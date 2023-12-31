import sys
import torch
import logging
import numpy as np

from IPython import embed
import matplotlib.pyplot as plt


logging.basicConfig(
	stream=sys.stderr,
	format="%(asctime)s - %(levelname)s - %(name)s - %(message)s ",
	datefmt="%d/%m/%Y %H:%M:%S",
	level=logging.INFO,
)
LOGGER = logging.getLogger(__name__)


class CURApprox(object):

	def __init__(self, rows, cols, row_idxs, col_idxs, approx_preference, A=None):
		super(CURApprox, self).__init__()
		# M :(n x m) = C U R : (n x kc) X (kc x kr) X (kr x m)

		self.n = cols.shape[0]
		self.m = rows.shape[1]

		self.row_idxs = row_idxs
		self.col_idxs = col_idxs

		self.C = cols # n x kc
		self.R = rows # kr x m
		
		self.approx_preference = approx_preference
		
		assert self._is_sorted(self.row_idxs), "row_idxs should be sorted"
		assert self._is_sorted(self.col_idxs), "col_idxs should be sorted"

		assert len(row_idxs) == self.R.shape[0]
		assert len(col_idxs) == self.C.shape[1]

		intersect_mat = self.C[row_idxs, :] # kr x kc

		# assert torch.eq(self.C[row_idxs, :], self.R[:, col_idxs]), "Invalid rows and cols as their intersection does not match"
		
		if A is not None: # A better conditioned way of estimating U matrix but this requires computing entire matrix A ahead of time.
			self.U = torch.tensor(np.linalg.pinv(self.C)) @ torch.tensor(A) @ torch.tensor(np.linalg.pinv(self.R))
		else:
			self.U = torch.tensor(np.linalg.pinv(intersect_mat)) # kc x kr
			
		self.latent_rows, self.latent_cols = self._build_latent_row_cols(C=self.C, U=self.U, R=self.R, approx_preference=self.approx_preference)

	@staticmethod
	def _is_sorted(idx_list):
		return all(i < j for i,j in zip(idx_list[:-1], idx_list[1:]))

	@staticmethod
	def _build_latent_row_cols(C, U, R, approx_preference):

		if approx_preference == "cols":
			latent_rows = C @ U # n x kr
			latent_cols = R # kr x m
		elif approx_preference == "rows":
			latent_rows = C # n x kc
			latent_cols = U @ R # kc x m
		else:
			raise NotImplementedError(f"approx_preference = {approx_preference} not supported")
		
		return latent_rows, latent_cols

	def get_rows(self, row_idxs):

		# len(row_idxs) x m) =  (len(row_idxs) x kr) X ( kr, m))
		ans = self.latent_rows[row_idxs,:] @ self.latent_cols
		return ans

	def get_cols(self, col_idxs):
		# n x len(col_idxs) =  (n x kr) X (kr, len(col_idxs))
		ans = self.latent_rows @ self.latent_cols[:, col_idxs]
		return ans

	def get(self, row_idxs, col_idxs):

		# len(row_idxs) x len(col_idxs) =  (len(row_idxs) x kr) X ( kr, len(col_idxs))
		ans = self.latent_rows[row_idxs,:] @ self.latent_cols[:, col_idxs]
		return ans

	def get_complete_col(self, sparse_cols):
		"""
		Take values in cols corresponding to anchor row indices and return complete cols
		:param sparse_cols:
		:return:
		"""
		if self.approx_preference != "cols":
			raise NotImplementedError("This is not designed to give good approx of cols as U matrix is multiplied w/ R matrix. Build index w/ approx_preference = cols instead.")
		# (n x *) = (n x kr) X (kr x *)
		dense_cols = self.latent_rows @ sparse_cols
		return dense_cols

	def topk_in_col(self, sparse_cols, k):
		"""
		Return top-k indices in these col(s)
		:return:
		"""

		return torch.topk(self.get_complete_col(sparse_cols=sparse_cols), k, dim=1)


	def get_complete_row(self, sparse_rows):
		"""
		Take values in rows corresponding to anchor col indices and return complete rows
		:param sparse_cols:
		:return:
		"""
		if self.approx_preference != "rows":
			raise NotImplementedError("This is not designed to give good approx of rows as C and U matrix are multiplied together. Build index w/ approx_preference = rows instead.")
		# (* x m) = (* x kr) X (kr x m)
		dense_rows = sparse_rows @ self.latent_cols
		return dense_rows

	def topk_in_row(self, sparse_rows, k):
		"""
		Return top-k indices in these row(s)
		:return:
		"""
		return torch.topk(self.get_complete_row(sparse_rows=sparse_rows), k, dim=1)


def plot_heat_map(val_matrix, row_vals, col_vals, metric, top_k, curr_res_dir, title=None, fname=None):
	"""
	Plot a heat map using give matrix and add x-/y-ticks and title
	:param val_matrix: Matrix for plotting heat map
	:param row_vals: y-ticks
	:param col_vals: x-ticks
	:param metric:
	:param top_k:
	:param curr_res_dir:
	:return:
	"""
	try:
		plt.clf()
		try:
			if np.max(val_matrix) > 100:
				fig, ax = plt.subplots(figsize=(12,12))
			else:
				fig, ax = plt.subplots(figsize=(8,8))
		except:
			fig, ax = plt.subplots(figsize=(8,8))
			
		im = ax.imshow(val_matrix)
		
	
		# We want to show all ticks...
		ax.set_xticks(np.arange(len(col_vals)))
		ax.set_yticks(np.arange(len(row_vals)))
		# ... and label them with the respective list entries
		ax.set_xticklabels(col_vals)
		ax.set_yticklabels(row_vals)
	
		# Rotate the tick labels and set their alignment.
		plt.setp(ax.get_xticklabels(), rotation=45, ha="right",
				 rotation_mode="anchor", fontsize=20)
		
		plt.setp(ax.get_yticklabels(), rotation=0, fontsize=20)
	
		# Loop over data dimensions and create text annotations.
		for i in range(len(row_vals)):
			for j in range(len(col_vals)):
				ax.text(j, i, "{:.1f}".format(val_matrix[i, j]),
						ha="center", va="center", color="w", fontsize=20)
	
		# ax.set_title(f"{metric} for topk={top_k}" if title is None else title)
		ax.set_xlabel("Number of anchor entities", fontsize=20)
		ax.set_ylabel("Number of anchor   mentions", fontsize=20)
		fig.tight_layout()
		if fname is None:
			plt.savefig(f"{curr_res_dir}/{metric}_{top_k}.pdf")
		else:
			plt.savefig(f"{curr_res_dir}/{fname}.pdf")
		plt.close()
	except Exception as e:
		embed()
		raise e


class SVDApprox(object):

	def __init__(self, A, approx_preference):
		super(SVDApprox, self).__init__()
		# M :(n x m) = SVD : (n x kc) X (kc x kr) X (kr x m)

		self.m = A.shape[1]
		self.truncate = 0.2
		self.coef = int(self.m * self.truncate)

		U, sigma, V = torch.svd(A)
		sigma = sigma[:self.coef]
		U = U[:, :self.coef]
		V = V[:, :self.coef]

		if approx_preference == 'rows':
			self.latent_rows = U
			self.latent_cols = torch.matmul(torch.diag_embed(sigma), V.mT)
		elif approx_preference == 'cols':
			self.latent_rows = torch.matmul(U, torch.diag_embed(self.sigma))
			self.latent_cols = V.mT
		else:
			NotImplementedError('no approx preference of that type {}' % approx_preference)


	def get_rows(self, row_idxs):

		# len(row_idxs) x m) =  (len(row_idxs) x kr) X ( kr, m))
		ans = self.latent_rows[row_idxs,:] @ self.latent_cols
		return ans


	def get_cols(self, col_idxs):
		# n x len(col_idxs) =  (n x kr) X (kr, len(col_idxs))
		ans = self.latent_rows @ self.latent_cols[:, col_idxs]
		return ans

	def get(self, row_idxs, col_idxs):

		# len(row_idxs) x len(col_idxs) =  (len(row_idxs) x kr) X ( kr, len(col_idxs))
		rows = self.latent_rows[row_idxs,:]
		cols = self.latent_cols[:, col_idxs]
		ans = rows @ cols
		return ans

	def get_complete_col(self, sparse_cols):
		"""
		Take values in cols corresponding to anchor row indices and return complete cols
		:param sparse_cols:
		:return:
		"""
		if self.approx_preference != "cols":
			raise NotImplementedError("This is not designed to give good approx of cols as U matrix is multiplied w/ R matrix. Build index w/ approx_preference = cols instead.")
		# (n x *) = (n x kr) X (kr x *)
		dense_cols = self.latent_rows @ sparse_cols
		return dense_cols

	def topk_in_col(self, sparse_cols, k):
		"""
		Return top-k indices in these col(s)
		:return:
		"""

		return torch.topk(self.get_complete_col(sparse_cols=sparse_cols), k, dim=1)


	def get_complete_row(self, sparse_rows):
		"""
		Take values in rows corresponding to anchor col indices and return complete rows
		:param sparse_cols:
		:return:
		"""
		if self.approx_preference != "rows":
			raise NotImplementedError("This is not designed to give good approx of rows as C and U matrix are multiplied together. Build index w/ approx_preference = rows instead.")
		# (* x m) = (* x kr) X (kr x m)
		dense_rows = sparse_rows @ self.latent_cols
		return dense_rows

	def topk_in_row(self, sparse_rows, k):
		"""
		Return top-k indices in these row(s)
		:return:
		"""
		return torch.topk(self.get_complete_row(sparse_rows=sparse_rows), k, dim=1)


class QRApprox(object):
    def __init__(self, A, approx_preference):
        """
        Initialize the QR matrix approximation.
        :param A: The original matrix to approximate.
        :param approx_preference: Preference for approximation ('rows' or 'cols').
        """
        super(QRApprox, self).__init__()

        self.m = A.shape[1]

        Q, R = torch.qr(torch.tensor(A, dtype=torch.float64))
        self.truncate = 0.2
        self.coef = int(self.m * self.truncate)

        Q = Q[:, :self.coef]
        R = R[:self.coef, :]

        if approx_preference == 'rows':
            self.latent_rows = Q
            self.latent_cols = R
        elif approx_preference == 'cols':
            self.latent_rows = torch.matmul(Q, torch.diag_embed(torch.diag(R)))
            self.latent_cols = torch.eye(self.m)[:, :self.coef]
        else:
            raise NotImplementedError('No approx preference of type {} found'.format(approx_preference))

    def get_rows(self, row_idxs):
        """
        Compute the approximation for specified row indices.
        :param row_idxs: Row indices to approximate.
        :return: Approximated rows.
        """
        ans = self.latent_rows[row_idxs, :] @ self.latent_cols
        return ans

    def get_cols(self, col_idxs):
        """
        Compute the approximation for specified column indices.
        :param col_idxs: Column indices to approximate.
        :return: Approximated columns.
        """
        ans = self.latent_rows @ self.latent_cols[:, col_idxs]
        return ans

    def get(self, row_idxs, col_idxs):
        """
        Compute the approximation for specified row and column indices.
        :param row_idxs: Row indices to approximate.
        :param col_idxs: Column indices to approximate.
        :return: Approximated matrix section.
        """
        rows = self.latent_rows[row_idxs, :]
        cols = self.latent_cols[:, col_idxs]
        ans = rows @ cols
        return ans

    def get_complete_col(self, sparse_cols):
        """
        Compute complete columns from given sparse columns.
        :param sparse_cols: Sparse columns.
        :return: Complete columns.
        """
        if self.approx_preference != "cols":
            raise NotImplementedError("Build index with approx_preference = 'cols' for this functionality.")
        dense_cols = self.latent_rows @ sparse_cols
        return dense_cols

    def topk_in_col(self, sparse_cols, k):
        """
        Find top-k indices in the approximated columns.
        :param sparse_cols: Sparse columns.
        :param k: Number of top indices to find.
        :return: Top-k indices.
        """
        return torch.topk(self.get_complete_col(sparse_cols=sparse_cols), k, dim=1)

    def get_complete_row(self, sparse_rows):
        """
        Compute complete rows from given sparse rows.
        :param sparse_rows: Sparse rows.
        :return: Complete rows.
        """
        if self.approx_preference != "rows":
            raise NotImplementedError("Build index with approx_preference = 'rows' for this functionality.")
        dense_rows = sparse_rows @ self.latent_cols
        return dense_rows

    def topk_in_row(self, sparse_rows, k):
        """
        Find top-k indices in the approximated rows.
        :param sparse_rows: Sparse rows.
        :param k: Number of top indices to find.
        :return: Top-k indices.
        """
        return torch.topk(self.get_complete_row(sparse_rows=sparse_rows), k, dim=1)		