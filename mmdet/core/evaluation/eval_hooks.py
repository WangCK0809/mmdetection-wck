import os
import os.path as osp
import time

import mmcv
import numpy as np
import torch
import torch.distributed as dist
from mmcv.parallel import collate, scatter
from mmcv.runner import Hook
from pycocotools.cocoeval import COCOeval
from torch.utils.data import Dataset

from mmdet import datasets
from .coco_utils import fast_eval_recall, results2json
from .mean_ap import eval_map
from .eval_miss_rate import eval_caltech_mr, eval_kaist_mr, eval_cvc_mr


"""
Author:Yuan Yuan
Date:2018/12/01
Description: change after_train_epoch()
"""


class DistEvalHook(Hook):

    def __init__(self, dataset, interval=1):
        if isinstance(dataset, Dataset):
            self.dataset = dataset
        elif isinstance(dataset, dict):
            self.dataset = datasets.build_dataset(dataset, {'test_mode': True})
        else:
            raise TypeError(
                'dataset must be a Dataset object or a dict, not {}'.format(
                    type(dataset)))
        self.interval = interval

    """
    Kai add this method.
    """
    def _barrier(self, rank, world_size):
        """Due to some issues with `torch.distributed.barrier()`, we have to
        implement this ugly barrier function.
        """
        if rank == 0:
            for i in range(1, world_size):
                tmp = osp.join(self.lock_dir, '{}.pkl'.format(i))
                while not (osp.exists(tmp)):
                    time.sleep(1)
            for i in range(1, world_size):
                tmp = osp.join(self.lock_dir, '{}.pkl'.format(i))
                os.remove(tmp)
        else:
            tmp = osp.join(self.lock_dir, '{}.pkl'.format(rank))
            mmcv.dump([], tmp)
            while osp.exists(tmp):
                time.sleep(1)

    def after_train_epoch(self, runner):
        if not self.every_n_epochs(runner, self.interval):
            return
        runner.model.eval()
        results = [None for _ in range(len(self.dataset))]
        if runner.rank == 0:
            prog_bar = mmcv.ProgressBar(len(self.dataset))
        for idx in range(runner.rank, len(self.dataset), runner.world_size):
            data = self.dataset[idx]
            data_gpu = scatter(
                collate([data], samples_per_gpu=1),
                [torch.cuda.current_device()])[0]

            # compute output
            with torch.no_grad():
                result = runner.model(
                    return_loss=False, rescale=True, **data_gpu)
            results[idx] = result

            """
            Yuan add following code for evaluating miss rate using matlab code.
            For each image, detection result will be written into it's corresponding text file.
            Matlab script will load those detection results and perform evaluation.
            It is finished with matlab engine on background.
            detection result -> text file -> matlab script
            """
            # image path
            img_path = self.dataset.img_infos[idx]['filename']
            res_path = img_path.replace('images', 'res')        # res : result
            # print()             # for debug
            # print(img_path)     # for debug
            # print(res_path)     # for debug
            if 'visible' in res_path:
                res_path = res_path.replace('/visible/', '/')
            res_path = res_path.replace('.jpg', '.txt')
            res_path = res_path.replace('.png', '.txt')
            # print(res_path)     # for debug
            if os.path.exists(res_path):
                os.remove(res_path)
            os.mknod(res_path)
            """
            For faster-rcnn, the result is a list, each element in list is result for a object class.
            In pedestrian detection, there is only one class.
            For RPN, the result is a numpy. The result of RPN is category-independent.
            """
            if isinstance(result, list):
                np.savetxt(res_path, result[0])
            else:
                np.savetxt(res_path, result)

            batch_size = runner.world_size
            for _ in range(batch_size):
                prog_bar.update()

        """
        yuan comment following code because of new evaluation method.
        """
        # if runner.rank == 0:
        #     print('\n')
        #     dist.barrier()
        #     for i in range(1, runner.world_size):
        #         tmp_file = osp.join(runner.work_dir, 'temp_{}.pkl'.format(i))
        #         tmp_results = mmcv.load(tmp_file)
        #         for idx in range(i, len(results), runner.world_size):
        #             results[idx] = tmp_results[idx]
        #         os.remove(tmp_file)
        #     self.evaluate(runner, results)
        # else:
        #     tmp_file = osp.join(runner.work_dir,
        #                         'temp_{}.pkl'.format(runner.rank))
        #     mmcv.dump(results, tmp_file)
        #     dist.barrier()
        """
        yuan add following line.
        """
        self.evaluate(runner, results)

        # dist.barrier()
        self._barrier(runner.rank, runner.world_size)

    def evaluate(self):
        raise NotImplementedError

# class DistEvalHook(Hook):
#
#     def __init__(self, dataset, interval=1):
#         if isinstance(dataset, Dataset):
#             self.dataset = dataset
#         elif isinstance(dataset, dict):
#             self.dataset = datasets.build_dataset(dataset, {'test_mode': True})
#         else:
#             raise TypeError(
#                 'dataset must be a Dataset object or a dict, not {}'.format(
#                     type(dataset)))
#         self.interval = interval
#
#     def after_train_epoch(self, runner):
#         if not self.every_n_epochs(runner, self.interval):
#             return
#         runner.model.eval()
#         results = [None for _ in range(len(self.dataset))]
#         if runner.rank == 0:
#             prog_bar = mmcv.ProgressBar(len(self.dataset))
#         for idx in range(runner.rank, len(self.dataset), runner.world_size):
#             data = self.dataset[idx]
#             data_gpu = scatter(
#                 collate([data], samples_per_gpu=1),
#                 [torch.cuda.current_device()])[0]
#
#             # compute output
#             with torch.no_grad():
#                 result = runner.model(
#                     return_loss=False, rescale=True, **data_gpu)
#             results[idx] = result
#
#             batch_size = runner.world_size
#             if runner.rank == 0:
#                 for _ in range(batch_size):
#                     prog_bar.update()
#
#         if runner.rank == 0:
#             print('\n')
#             dist.barrier()
#             for i in range(1, runner.world_size):
#                 tmp_file = osp.join(runner.work_dir, 'temp_{}.pkl'.format(i))
#                 tmp_results = mmcv.load(tmp_file)
#                 for idx in range(i, len(results), runner.world_size):
#                     results[idx] = tmp_results[idx]
#                 os.remove(tmp_file)
#             self.evaluate(runner, results)
#         else:
#             tmp_file = osp.join(runner.work_dir,
#                                 'temp_{}.pkl'.format(runner.rank))
#             mmcv.dump(results, tmp_file)
#             dist.barrier()
#         dist.barrier()
#
#     def evaluate(self):
#         raise NotImplementedError


"""
Author:Yuan Yuan
Date:2019/02/11
Description:these three hook classes are used for launching Matlab evaluation script.
"""


class DistEvalCaltechMR(DistEvalHook):
    def evaluate(self, runner, results):
        eval_caltech_mr()


class DistEvalKaistMR(DistEvalHook):
    def evaluate(self, runner, results):
        eval_kaist_mr()


class DistEvalCvcMR(DistEvalHook):
    def evaluate(self, ruuner, results):
        eval_cvc_mr()


class DistEvalmAPHook(DistEvalHook):

    def evaluate(self, runner, results):
        gt_bboxes = []
        gt_labels = []
        gt_ignore = []
        for i in range(len(self.dataset)):
            ann = self.dataset.get_ann_info(i)
            bboxes = ann['bboxes']
            labels = ann['labels']
            if 'bboxes_ignore' in ann:
                ignore = np.concatenate([
                    np.zeros(bboxes.shape[0], dtype=np.bool),
                    np.ones(ann['bboxes_ignore'].shape[0], dtype=np.bool)
                ])
                gt_ignore.append(ignore)
                bboxes = np.vstack([bboxes, ann['bboxes_ignore']])
                labels = np.concatenate([labels, ann['labels_ignore']])
            gt_bboxes.append(bboxes)
            gt_labels.append(labels)
        if not gt_ignore:
            gt_ignore = None
        # If the dataset is VOC2007, then use 11 points mAP evaluation.
        if hasattr(self.dataset, 'year') and self.dataset.year == 2007:
            ds_name = 'voc07'
        else:
            ds_name = self.dataset.CLASSES
        mean_ap, eval_results = eval_map(
            results,
            gt_bboxes,
            gt_labels,
            gt_ignore=gt_ignore,
            scale_ranges=None,
            iou_thr=0.5,
            dataset=ds_name,
            print_summary=True)
        runner.log_buffer.output['mAP'] = mean_ap
        runner.log_buffer.ready = True


class CocoDistEvalRecallHook(DistEvalHook):

    def __init__(self,
                 dataset,
                 interval=1,
                 proposal_nums=(100, 300, 1000),
                 iou_thrs=np.arange(0.5, 0.96, 0.05)):
        super(CocoDistEvalRecallHook, self).__init__(
            dataset, interval=interval)
        self.proposal_nums = np.array(proposal_nums, dtype=np.int32)
        self.iou_thrs = np.array(iou_thrs, dtype=np.float32)

    def evaluate(self, runner, results):
        # the official coco evaluation is too slow, here we use our own
        # implementation instead, which may get slightly different results
        ar = fast_eval_recall(results, self.dataset.coco, self.proposal_nums,
                              self.iou_thrs)
        for i, num in enumerate(self.proposal_nums):
            runner.log_buffer.output['AR@{}'.format(num)] = ar[i]
        runner.log_buffer.ready = True


class CocoDistEvalmAPHook(DistEvalHook):

    def evaluate(self, runner, results):
        tmp_file = osp.join(runner.work_dir, 'temp_0')
        result_files = results2json(self.dataset, results, tmp_file)

        res_types = ['bbox', 'segm'
                     ] if runner.model.module.with_mask else ['bbox']
        cocoGt = self.dataset.coco
        imgIds = cocoGt.getImgIds()
        for res_type in res_types:
            try:
                cocoDt = cocoGt.loadRes(result_files[res_type])
            except IndexError:
                print('No prediction found.')
                break
            iou_type = res_type
            cocoEval = COCOeval(cocoGt, cocoDt, iou_type)
            cocoEval.params.imgIds = imgIds
            cocoEval.evaluate()
            cocoEval.accumulate()
            cocoEval.summarize()
            metrics = ['mAP', 'mAP_50', 'mAP_75', 'mAP_s', 'mAP_m', 'mAP_l']
            for i in range(len(metrics)):
                key = '{}_{}'.format(res_type, metrics[i])
                val = float('{:.3f}'.format(cocoEval.stats[i]))
                runner.log_buffer.output[key] = val
            runner.log_buffer.output['{}_mAP_copypaste'.format(res_type)] = (
                '{ap[0]:.3f} {ap[1]:.3f} {ap[2]:.3f} {ap[3]:.3f} '
                '{ap[4]:.3f} {ap[5]:.3f}').format(ap=cocoEval.stats[:6])
        runner.log_buffer.ready = True
        for res_type in res_types:
            os.remove(result_files[res_type])
