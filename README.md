# 无人驾驶小车项目

## 目录结构

```
Project_DriverlessCar/
├── tracking/               # 巡线模块（传统 CV）
│   ├── line_tracker.py     #   主程序：摄像头→图像处理→扫线→偏差→串口
│   └── simulate_track.py   #   模拟测试：生成虚拟赛道，验证算法
│
├── ai_training/            # AI 模型训练（PaddleX 高层 API）
│   ├── train_paddlex.py    #   ★ 训练脚本（PicoDet-S 轻量检测模型）
│   ├── _legacy/            #   旧版手写框架归档（已废弃）
│   ├── dataset/            #   数据集（VOC 格式）
│   │   ├── images/         #     2035 张 JPG
│   │   ├── annotations/    #     2035 个 XML
│   │   ├── label_list.txt  #     8 个类别
│   │   ├── train_list.txt  #     1625 条训练数据
│   │   └── val_list.txt    #     410 条验证数据
│   └── output_paddlex/     #   训练产物（PaddleX 自动生成）
│
├── decision/               # 决策层（巡线 error + AI 检测 → 控制指令）
│   └── decide.py           #   决策函数
│
├── communication/          # 通讯层（上位机 ↔ 单片机）
│   └── serial_handler.py   #   串口收发封装
│
├── mcu/                    # 单片机代码（GD32F103C8T6）
│   └── gd32_control.c      #   电机控制 + 串口接收
│
└── docs/                   # 文档
    └── architecture.md     #   系统架构说明
```

## 六层架构

```
S320 摄像头
    ↓
[2] 图像预处理（裁切、二值化）
    ↓
[3] 扫线（逐行找路面区域）
    ↓
[4] 偏差计算（路中心 - 画面中心 = error）
    ↓       ← AI 检测（后台线程，检测行人/锥桶/斑马线）
    ↓
[5] 决策层（error + 检测结果 → 控制指令）
    ↓
[6] 串口 → GD32 单片机 → 电机
```

## 进度

| 模块 | 状态 |
|------|:--:|
| 巡线（二~四层） | ✅ |
| 模拟验证 | ✅ |
| AI 训练框架 | ✅ |
| AI 模型 | 🔄 训练中 |
| 决策层 | 🔄 骨架有，待完善 |
| 串口通讯 | 🔄 骨架有，待完善 |
| 单片机 | ❌ |
