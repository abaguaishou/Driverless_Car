# ============================
# 巡线模块 — 集中配置文件
# 所有可调参数放这里，改一个数字全局生效
# ============================

# ---------- 硬件 ----------
CAMERA_INDEX      = 0              # 摄像头编号（0=第一个摄像头）
SERIAL_PORT       = "COM3"         # 串口号（插上单片机后去设备管理器查）
SERIAL_BAUDRATE   = 115200         # 波特率（要和单片机 C 代码一致）

# ---------- 图像预处理 ----------
CROP_TOP          = 225            # 裁掉上面多少行（天空部分）
CROP_BOTTOM       = 480            # 保留到第几行（去掉太近的地面）
THRESHOLD_VALUE   = 80             # 二值化阈值（0-255，低于此值为路面）
THRESHOLD_MAX     = 225            # 二值化最大值

# ---------- 扫线 ----------
LINE_SCAN_STEP    = 5              # 隔几行扫一次（越大越快，越粗）
MIN_LINE_PIXELS   = 8              # 一行里至少几个白像素才算有效路面
LANE_HALF_WIDTH   = 100            # 预估的半条车道宽度（像素），单线丢失时用

# ---------- 障碍检测 ----------
OBSTACLE_FRAMES   = 3              # 连续 N 帧确认才触发（防误判）
PERSON_HEIGHT_MIN = 150            # 行人的框高阈值（像素，越小越早触发）
CONE_HEIGHT_MIN   = 100            # 锥桶的框高阈值

# ---------- 路标检测 ----------
SIGN_HEIGHT_MIN   = 60             # 路标框高最低门槛（太小=太远，忽略）
SIGN_HISTORY_MIN  = 5              # 至少攒够多少帧才判断（>此值 + 最后3帧-1 → 触发）
SIGN_CLASSES      = ["crosswalk", "bridge", "bump"]   # 哪些类别算路标
CROSSWALK_CMD     = "crosswalk_task"
BRIDGE_CMD        = "bridge_task"
BUMP_CMD          = "bump_task"

# ---------- AI 线程 ----------
AI_THREAD_SLEEP   = 0.1            # AI 线程每轮推理后歇多久（秒）
AI_FRAME_TIMEOUT  = 0.01           # AI 线程等主线程丢帧的超时（秒）
