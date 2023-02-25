import os
import sys

sys.path.append(os.pardir)

import threading
from typing import List

import numpy as np
from tree_node import Node


def xgboost_compute_gain(
    left_grad: List[float],
    right_grad: List[float],
    left_hess: List[float],
    right_hess: List[float],
    gam: float,
    lam: float,
) -> float:
    left_gain = 0.0
    right_gain = 0.0
    base_gain = 0.0

    for c in range(len(left_grad)):
        left_gain += (left_grad[c] ** 2) / (left_hess[c] + lam)
        right_gain += (right_grad[c] ** 2) / (right_hess[c] + lam)
        base_gain += ((left_grad[c] + right_grad[c]) ** 2) / (
            left_hess[c] + right_hess[c] + lam
        )

    return 0.5 * (left_gain + right_gain - base_gain) - gam


def xgboost_compute_weight(
    row_count: int,
    gradient: List[List[float]],
    hessian: List[List[float]],
    idxs: List[int],
    lam: float,
) -> List[float]:
    grad_dim = len(gradient[0])
    sum_grad = [0.0 for _ in range(grad_dim)]
    sum_hess = [0.0 for _ in range(grad_dim)]
    node_weights = [0.0 for _ in range(grad_dim)]

    for i in range(row_count):
        for c in range(grad_dim):
            sum_grad[c] += gradient[idxs[i]][c]
            sum_hess[c] += hessian[idxs[i]][c]

    for c in range(grad_dim):
        node_weights[c] = -1.0 * (sum_grad[c] / (sum_hess[c] + lam))

    return node_weights


class XGBoostNode(Node):
    def __init__(
        self,
        parties_: list,
        y_: list,
        num_classes_: int,
        gradient_: list,
        hessian_: list,
        idxs_: list,
        prior_: list,
        min_child_weight_: float,
        lam_: float,
        gamma_: float,
        eps_: float,
        depth_: int,
        mi_bound_: float,
        active_party_id_: int = -1,
        use_only_active_party_: bool = False,
        n_job_: int = 1,
    ):
        super(XGBoostNode, self).__init__(
            parties_,
            y_,
            num_classes_,
            gradient_,
            hessian_,
            idxs_,
            prior_,
            min_child_weight_,
            lam_,
            gamma_,
            eps_,
            depth_,
            mi_bound_,
            active_party_id_,
            use_only_active_party_,
            n_job_,
        )

        self.parties = parties_
        self.y = y_
        self.prior = prior_
        self.gradient = gradient_
        self.hessian = hessian_
        self.min_child_weight = min_child_weight_
        self.lam = lam_
        self.gamma = gamma_
        self.eps = eps_
        self.mi_bound = mi_bound_
        self.best_entropy = None
        self.use_only_active_party = use_only_active_party_
        self.left = None
        self.right = None
        self.num_classes = num_classes_
        self.entire_datasetsize = len(self.y)
        self.entire_class_cnt = np.zeros(self.num_classes)
        for i in range(self.entire_datasetsize):
            self.entire_class_cnt[int(self.y[i])] += 1.0

        try:
            if self.use_only_active_party and self.active_party_id > len(self.parties):
                raise ValueError("invalid active_party_id")
        except ValueError as e:
            print(e)

        self.val = self.compute_weight()

        if self.is_leaf():
            self.is_leaf_flag = True
        else:
            self.is_leaf_flag = False

        if not self.is_leaf_flag:
            best_split = self.find_split()
            party_id = best_split[0]
            if party_id != -1:
                self.party_id = party_id
                self.record_id = self.parties[self.party_id].insert_lookup_table(
                    best_split[1], best_split[2]
                )
                self.make_children_nodes(best_split[0], best_split[1], best_split[2])
            else:
                self.is_leaf_flag = True

    def get_idxs(self):
        return self.idxs

    def get_party_id(self):
        return self.party_id

    def get_record_id(self):
        return self.record_id

    def get_val(self):
        return self.val

    def get_score(self):
        return self.score

    def get_left(self):
        return self.left

    def get_right(self):
        return self.right

    def get_num_parties(self):
        return len(self.parties)

    def compute_weight(self):
        return xgboost_compute_weight(
            self.row_count, self.gradient, self.hessian, self.idxs, self.lam
        )

    def compute_gain(self, left_grad, right_grad, left_hess, right_hess):
        return xgboost_compute_gain(
            left_grad, right_grad, left_hess, right_hess, self.gamma, self.lam
        )

    def find_split_per_party(
        self,
        party_id_start,
        temp_num_parties,
        sum_grad,
        sum_hess,
        tot_cnt,
        temp_y_class_cnt,
    ):
        temp_left_class_cnt = [0 for _ in range(self.num_classes)]
        temp_right_class_cnt = [0 for _ in range(self.num_classes)]
        grad_dim = len(sum_grad)

        for temp_party_id in range(party_id_start, party_id_start + temp_num_parties):
            search_results = self.parties[
                temp_party_id
            ].greedy_search_split_from_pointer(
                self.gradient, self.hessian, self.y, self.idxs
            )
            temp_score, temp_entropy = 0, 0
            temp_left_grad, temp_left_hess, temp_right_grad, temp_right_hess = (
                [0] * grad_dim,
                [0] * grad_dim,
                [0] * grad_dim,
                [0] * grad_dim,
            )
            temp_left_size, temp_right_size = 0, 0
            skip_flag = False

            for j in range(len(search_results)):
                temp_score = 0
                temp_entropy = 0
                temp_left_size = 0
                temp_right_size = 0

                for c in range(grad_dim):
                    temp_left_grad[c] = 0
                    temp_left_hess[c] = 0

                for c in range(self.num_classes):
                    temp_left_class_cnt[c] = 0
                    temp_right_class_cnt[c] = 0

                for k in range(len(search_results[j])):
                    for c in range(grad_dim):
                        temp_left_grad[c] += search_results[j][k][0][c]
                        temp_left_hess[c] += search_results[j][k][1][c]

                    temp_left_size += search_results[j][k][2]
                    temp_right_size = tot_cnt - temp_left_size

                    for c in range(self.num_classes):
                        temp_left_class_cnt[c] += search_results[j][k][3][c]
                        temp_right_class_cnt[c] = (
                            temp_y_class_cnt[c] - temp_left_class_cnt[c]
                        )

                    skip_flag = False
                    for c in range(grad_dim):
                        if (
                            temp_left_hess[c] < self.min_child_weight
                            or sum_hess[c] - temp_left_hess[c] < self.min_child_weight
                        ):
                            skip_flag = True

                    if skip_flag:
                        continue

                    for c in range(grad_dim):
                        temp_right_grad[c] = sum_grad[c] - temp_left_grad[c]
                        temp_right_hess[c] = sum_hess[c] - temp_left_hess[c]

                    temp_score = self.compute_gain(
                        temp_left_grad, temp_right_grad, temp_left_hess, temp_right_hess
                    )

                    if temp_score > self.best_score:
                        self.best_score = temp_score
                        self.best_entropy = temp_entropy
                        self.best_party_id = temp_party_id
                        self.best_col_id = j
                        self.best_threshold_id = k

    def find_split(self):
        sum_grad = [0 for _ in range(len(self.gradient[0]))]
        sum_hess = [0 for _ in range(len(self.hessian[0]))]

        for i in range(self.row_count):
            for c in range(len(sum_grad)):
                sum_grad[c] += self.gradient[self.idxs[i]][c]
                sum_hess[c] += self.hessian[self.idxs[i]][c]

        tot_cnt = self.row_count
        temp_y_class_cnt = [0 for _ in range(self.num_classes)]
        for r in range(self.row_count):
            temp_y_class_cnt[int(self.y[self.idxs[r]])] += 1

        if self.use_only_active_party:
            self.find_split_per_party(
                self.active_party_id, 1, sum_grad, sum_hess, tot_cnt, temp_y_class_cnt
            )
        else:
            if self.n_job == 1:
                self.find_split_per_party(
                    0, self.num_parties, sum_grad, sum_hess, tot_cnt, temp_y_class_cnt
                )
            else:
                num_parties_per_thread = self.get_num_parties_per_process(
                    self.n_job, self.num_parties
                )

                cnt_parties = 0
                threads_parties = []
                for i in range(self.n_job):
                    local_num_parties = num_parties_per_thread[i]
                    temp_th = threading.Thread(
                        target=self.find_split_per_party,
                        args=(
                            cnt_parties,
                            local_num_parties,
                            sum_grad,
                            sum_hess,
                            tot_cnt,
                            temp_y_class_cnt,
                        ),
                    )
                    threads_parties.append(temp_th)
                    cnt_parties += num_parties_per_thread[i]

                for i in range(self.num_parties):
                    threads_parties[i].start()

                for i in range(self.num_parties):
                    threads_parties[i].join()

        self.score = self.best_score
        return self.best_party_id, self.best_col_id, self.best_threshold_id

    def make_children_nodes(self, best_party_id, best_col_id, best_threshold_id):
        left_idxs = self.parties[best_party_id].split_rows(
            self.idxs, best_col_id, best_threshold_id
        )
        right_idxs = []
        for i in range(self.row_count):
            if not any(x == self.idxs[i] for x in left_idxs):
                right_idxs.append(self.idxs[i])

        left_is_satisfied_lmir_cond = False  # is_satisfied_with_lmir_bound_from_pointer(num_classes, mi_bound, y, entire_class_cnt, prior, left_idxs)
        right_is_satisfied_lmir_cond = False  # is_satisfied_with_lmir_bound_from_pointer(num_classes, mi_bound, y, entire_class_cnt, prior, right_idxs)

        left = XGBoostNode(
            self.parties,
            self.y,
            self.num_classes,
            self.gradient,
            self.hessian,
            self.left_idxs,
            self.prior,
            self.min_child_weight,
            self.lam,
            self.gamma,
            self.eps,
            self.depth - 1,
            self.mi_bound,
            self.active_party_id,
            (self.use_only_active_party or (not left_is_satisfied_lmir_cond)),
            self.n_job,
        )
        if left.is_leaf_flag == 1:
            left.party_id = self.party_id
        right = XGBoostNode(
            self.parties,
            self.y,
            self.num_classes,
            self.gradient,
            self.hessian,
            self.right_idxs,
            self.prior,
            self.min_child_weight,
            self.lam,
            self.gamma,
            self.eps,
            self.depth - 1,
            self.mi_bound,
            self.active_party_id,
            (self.use_only_active_party or (not right_is_satisfied_lmir_cond)),
            self.n_job,
        )
        if right.is_leaf_flag == 1:
            right.party_id = self.party_id

        # Notice: this flag only supports for the case of two parties
        if (
            left.is_leaf_flag == 1
            and right.is_leaf_flag == 1
            and self.party_id == self.active_party_id
        ):
            left.not_splitted_flag = True
            right.not_splitted_flag = True

        # Clear unused index
        if not (
            (left.not_splitted_flag and right.not_splitted_flag)
            or (
                left.lmir_flag_exclude_passive_parties
                and right.lmir_flag_exclude_passive_parties
            )
        ):
            self.idxs = []

    def is_leaf(self):
        if self.is_leaf_flag == -1:
            return self.is_pure() or self.score == np.inf or self.depth <= 0
        else:
            return self.is_leaf_flag == 1

    def is_pure(self):
        if self.is_pure_flag == -1:
            s = set()
            for i in range(self.row_count):
                if self.y[self.idxs[i]] not in s:
                    s.add(self.y[self.idxs[i]])
                    if len(s) == 2:
                        is_pure_flag = 0
                        return False
            is_pure_flag = 1
            return True
        else:
            return is_pure_flag == 1
