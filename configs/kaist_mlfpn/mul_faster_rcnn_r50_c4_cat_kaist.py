# model settings
model = dict(
    type='FasterRCNNMul',
    pretrained='torchvision://resnet50',
    backbone=dict(
        type='MulCatResnet',
        depth=50,
        num_stages=4,
        strides=(1, 2, 2, 1),
        dilations=(1, 1, 1, 1),
        out_indices=(3,),
        stage_with_dcn=(False, False, False, False),
        frozen_stages=1,
        style='pytorch'
    ),
    neck=None,
    rpn_head=dict(
        type='RPNHead',
        in_channels=2048,
        feat_channels=256,
        anchor_scales=[4, 6, 8, 10, 12, 14],
        anchor_ratios=[1.0 / 0.5, 1.0],
        anchor_strides=[16],
        target_means=[.0, .0, .0, .0],
        target_stds=[1.0, 1.0, 1.0, 1.0],
        # use_sigmoid_cls=True
        loss_cls=dict(
            type='CrossEntropyLoss', use_sigmoid=True, loss_weight=1.0),
        loss_bbox=dict(type='SmoothL1Loss', beta=1.0 / 9.0, loss_weight=1.0)),
    bbox_roi_extractor=dict(
        type='SingleRoIExtractor',
        roi_layer=dict(type='RoIAlign', out_size=7, sample_num=-1),
        out_channels=128,
        featmap_strides=[16]),
    bbox_head=dict(
        type='SharedFCBBoxHead',
        num_fcs=2,
        in_channels=2048,
        fc_out_channels=256,
        roi_feat_size=7,
        num_classes=2,  # background and pederstrian
        target_means=[0., 0., 0., 0.],
        target_stds=[0.1, 0.1, 0.2, 0.2],
        reg_class_agnostic=True,
        loss_cls=dict(
            type='CrossEntropyLoss', use_sigmoid=False, loss_weight=1.0),
        loss_bbox=dict(type='SmoothL1Loss', beta=1.0, loss_weight=1.0)))

# model training and testing settings
train_cfg = dict(
    rpn=dict(
        assigner=dict(
            type='MaxIoUAssigner',
            pos_iou_thr=0.5,
            neg_iou_thr=0.3,
            min_pos_iou=0.3,
            ignore_iof_thr=-1),
        sampler=dict(
            type='RandomSampler',
            num=120,
            pos_fraction=1.0 / 4,
            neg_pos_ub=-1,
            add_gt_as_proposals=False,
            pos_balance_sampling=False,
            neg_balance_thr=0),
        allowed_border=0,
        pos_weight=-1,
        smoothl1_beta=1.0,
        debug=False,
        nms=dict(
            nms_across_levels=False,
            nms_pre=5000,
            nms_post=5000,
            max_num=100,
            nms_thr=0.7,
            min_bbox_size=0)),
    rcnn=dict(
        assigner=dict(
            type='MaxIoUAssigner',
            pos_iou_thr=0.5,
            neg_iou_thr=0.3,
            min_pos_iou=0.3,
            ignore_iof_thr=-1),
        sampler=dict(
            type='RandomSampler',
            num=64,
            pos_fraction=0.25,
            neg_pos_ub=-1,
            add_gt_as_proposals=True),
        pos_weight=-1,
        debug=False,))
test_cfg = dict(
    rpn=dict(
        nms_across_levels=False,
        nms_pre=10000,
        nms_post=10000,
        max_num=300,
        nms_thr=0.7,
        min_bbox_size=0),
    rcnn=dict(
        score_thr=0.1, nms=dict(type='nms', iou_thr=0.5), max_per_img=40))

# dataset settings
dataset_type = 'KaistDataset'
data_root = '/media/ser248/3rd/WangCK/Data/datasets/kaist_mlfpn-rgbt/'
img_norm_cfg = dict(
    mean=[123.675, 116.28, 103.53], std=[58.395, 57.12, 57.375], to_rgb=True)
img_norm_cfg_t = dict(
    mean=[123.675, 123.675, 123.675], std=[58.395, 58.395, 58.395], to_rgb=False)
train_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='LoadAnnotations', with_bbox=True),
    dict(type='Resize', img_scale=(960, 768), keep_ratio=True),
    dict(type='RandomFlip', flip_ratio=0.5),
    # dict(type='Normalize', **img_norm_cfg),
    dict(type='Pad', size_divisor=None),        # kai change
    dict(type='DefaultFormatBundle'),
    dict(type='Collect', keys=['img', 'gt_bboxes', 'gt_labels']),
]
test_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(
        type='MultiScaleFlipAug',
        img_scale=(960, 768),      # diff
        flip=False,
        transforms=[
            dict(type='Resize', keep_ratio=True),
            dict(type='RandomFlip'),
            # dict(type='Normalize', **img_norm_cfg),
            dict(type='Pad', size_divisor=None),        # kai change
            dict(type='ImageToTensor', keys=['img']),
            dict(type='Collect', keys=['img']),
        ])
]
data = dict(
    imgs_per_gpu=2,
    workers_per_gpu=2,
    train=dict(
        type=dataset_type,
        ann_file=data_root + 'annotations-pkl/train-all.pkl',
        img_prefix=data_root + 'images/',
        img_norm_cfg=img_norm_cfg,
        img_norm_cfg_t=img_norm_cfg_t,
        size_divisor=None,
        flip_ratio=0.5,
        with_mask=False,
        with_crowd=True,
        with_label=True,        # 以上5行因为版本原因，可能传入方式需要改变
        pipeline=train_pipeline),
    val=dict(
        type=dataset_type,
        ann_file=data_root + 'annotations-pkl/test-all.pkl',
        img_prefix=data_root + 'images/',
        img_norm_cfg=img_norm_cfg,
        img_norm_cfg_t=img_norm_cfg_t,
        with_mask=False,
        with_crowd=True,
        with_label=True,
        pipeline=test_pipeline),
    test=dict(
        type=dataset_type,
        ann_file=data_root + 'annotations-pkl/test-all.pkl',
        img_prefix=data_root + 'images/',
        img_norm_cfg=img_norm_cfg,
        size_divisor=None,
        flip_ratio=0,
        with_mask=False,
        with_label=False,
        pipeline=test_pipeline,
        test_mode=True))

# optimizer
optimizer = dict(type='SGD', lr=0.001, momentum=0.9, weight_decay=0.0001)
optimizer_config = dict(grad_clip=dict(max_norm=35, norm_type=2))

# learning policy
lr_config = dict(
    policy='step',
    # warmup='linear',
    # warmup_iters=2000,
    # warmup_ratio=1.0 / 3,
    step=[4, 8])
checkpoint_config = dict(interval=1)

# yapf:disable
log_config = dict(
    interval=1000,
    hooks=[
        dict(type='TextLoggerHook'),
        # dict(type='TensorboardLoggerHook')
    ])
# yapf:enable

# runtime settings
total_epochs = 25
dist_params = dict(backend='nccl')
log_level = 'INFO'
work_dir = '/media/ser248/3rd/WangCK/Data/work_dirs/mul_faster_rcnn_r50_c4_cat_kaist'
load_from = None
resume_from = None
workflow = [('train', 1)]
