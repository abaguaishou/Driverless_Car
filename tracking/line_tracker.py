import cv2
import numpy as np

#========================================串口初始化=========================================

# 修改：UART配置留空；确认CarDo固件协议及控制模式后填写。
import struct
import math
try:
    import serial
except ImportError:
    serial = None  # 未安装pyserial时仍可做图像调试。

COM_PORT = ""            # 待填，例如 "COM3" 或 "/dev/ttyUSB0"
BAUT_RATE = None          # 待填，必须与CarDo一致
UART_ENABLED = False     # 填好参数、确认协议后改为True
UART_WRITE_TIMEOUT = 0.1 # 秒，防止发送无限阻塞
# 修改：以下参数不能由像素偏差直接猜测，需按实际车辆标定。
DRIVE_SPEED = None        # 待填；项目示例中闭环为m/s，开环为占空比，须核实固件
STEER_CENTER = None       # 待填，直行舵机PWM
STEER_MIN = None          # 待填，车辆允许的最小PWM
STEER_MAX = None          # 待填，车辆允许的最大PWM
STEER_KP = None           # 待填，PWM/像素；正负号由实际转向决定

ser = None

def Open_UART():
    # 修改：配置未完成时只运行图像处理，不自动选择端口或发送。
    if not UART_ENABLED:
        print("UART未启用：仅运行图像处理")
        return None
    if serial is None:
        print("UART未启用：请安装pyserial")
        return None
    values = (DRIVE_SPEED, STEER_CENTER, STEER_MIN, STEER_MAX, STEER_KP)
    if (not isinstance(COM_PORT, str) or not COM_PORT.strip()
            or type(BAUT_RATE) is not int or BAUT_RATE <= 0
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
        print("UART配置未填写完整：仅运行图像处理")
        return None
    if (not 0 <= STEER_MIN <= STEER_CENTER <= STEER_MAX <= 65535
            or any(int(v) != v for v in (STEER_MIN, STEER_CENTER, STEER_MAX))
            or DRIVE_SPEED < 0 or STEER_KP == 0):
        print("UART控制参数无效：检查PWM范围、速度和转向系数")
        return None
    try:
        port = serial.Serial(COM_PORT, BAUT_RATE, bytesize=serial.EIGHTBITS,
                             parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                             timeout=0.1, write_timeout=UART_WRITE_TIMEOUT,
                             xonxoff=False, rtscts=False, dsrdtr=False)
        print("串口已打开", COM_PORT, BAUT_RATE, "8N1")
        return port
    except (serial.SerialException, OSError, ValueError) as exc:
        print("串口打开失败，仅运行图像处理：", exc)
        return None

#========================================参数声明===========================================

Threshold = 180          # 修改：保留原阈值；选取暗色区域，需按实际画面调节
ROI_UP = 225             #裁切起点：ROI 从第225行到实际画面底部（修改）
Step = 3                 #每隔几行扫一次，隔行扫描省时间
Min_Line_Pix = 30        #一行里亮像素少于这个数，就认为这行不算有效路
Bad_Distance = 25        #离拟合直线超过这个像素数的点，当坏点扔掉
Min_Valid_Rows = 5       #有效行少于这个数，就当作线丢了
Near_Weight = 3          #越靠近车头的行，拟合时权重越大
Lost_Keep_Frame = 5      # 修改：区分短/长丢线状态；UART对两种丢线均发送零速度

# 修改：区段跟踪参数；以下是调试初值，像素阈值以640像素宽画面为基准。
Max_Road_Width_Ratio = 0.80  # 过宽区域可能是背景；不把整幅暗图当道路
Max_Center_Jump = 18         # 相邻采样行中心允许跳动量
Max_Width_Change = 0.35      # 相邻有效行宽度相对变化上限
Initial_Search_Ratio = 0.25 # 底部初次搜索距种子中心的最大范围
Max_Missing_Rows = 3        # 最多跨过3个缺失采样行，不能跨越大片未知区域
Ambiguity_Margin = 8        # 两个候选距离近似相同时拒绝盲选
Lookahead_Ratio = 0.55      # ROI内前视位置：0在顶部，1在底部
Fit_Half_Window = 60        # 前视行上下局部拟合半窗口（480像素高基准）
Min_Fit_Span = 30           # 有效点必须覆盖足够高度
Max_Fit_RMSE = 12           # 拟合误差过大时按丢线处理

#============================硬件初始化======================================
cap = cv2.VideoCapture(0)       #摄像头初始化

#====================================================函数分装=========================================================

# 逐行选择连续暗色路面，使用上一行中点引导搜索。
# 边界必须在画面内可见；单侧出画面时不以画面边缘伪造边界。
def Find_Center(Ima_Bin, Seed_X=None):
    height, width = Ima_Bin.shape
    scale = width / 640.0
    min_width = max(3, int(Min_Line_Pix * scale))
    max_width = width * Max_Road_Width_Ratio
    previous = width / 2 if Seed_X is None else float(Seed_X)
    previous_width = None
    xs, ys = [], []
    missing = 0
    for y in range(height - 1, -1, -Step):
        row = (Ima_Bin[y] > 0).astype(np.int8)
        changes = np.diff(np.pad(row, (1, 1)))
        lefts = np.flatnonzero(changes == 1)
        rights = np.flatnonzero(changes == -1) - 1
        candidates = []
        for left, right in zip(lefts, rights):
            road_width = right - left + 1
            if left == 0 or right == width - 1 or not min_width <= road_width <= max_width:
                continue
            center = (left + right) / 2.0
            distance = abs(center - previous)
            if previous_width is None:
                if distance > width * Initial_Search_Ratio:
                    continue
            else:
                if distance > Max_Center_Jump * scale * (missing + 1):
                    continue
                if abs(road_width - previous_width) / previous_width > Max_Width_Change:
                    continue
            candidates.append((distance, center, road_width))
        candidates.sort()
        #岔路等出现两个同样合理的候选时，不武断选择方向。
        if (not candidates or (len(candidates) > 1
                and candidates[1][0] - candidates[0][0] < Ambiguity_Margin * scale)):
            missing += 1
            if missing > Max_Missing_Rows:
                break
            continue
        _, previous, previous_width = candidates[0]
        xs.append(previous)
        ys.append(y + ROI_UP)
        missing = 0
    return xs, ys


# 仅拟合前视位置附近的道路，避免用一条直线强行表示整个弯道。
def Center_Line(Center_ys, Center_xs, Target_Y, Frame_Height):
    ys = np.asarray(Center_ys, dtype=float)
    xs = np.asarray(Center_xs, dtype=float)
    if (ys.ndim != 1 or xs.ndim != 1 or len(ys) != len(xs)
            or len(ys) < Min_Valid_Rows
            or not np.all(np.isfinite(ys)) or not np.all(np.isfinite(xs))):
        return None
    scale = Frame_Height / 480.0
    local = np.abs(ys - Target_Y) <= Fit_Half_Window * scale
    ys, xs = ys[local], xs[local]
    def supported(y):
        return (len(y) >= Min_Valid_Rows and np.ptp(y) >= Min_Fit_Span * scale
                and y.min() <= Target_Y <= y.max())
    # 前视点必须被实际采样点包围，不允许向未知区域远距离外推。
    if not supported(ys):
        return None
    relative_y = ys - Target_Y
    a, b = np.polyfit(relative_y, xs, 1)
    keep = np.abs(a * relative_y + b - xs) <= Bad_Distance
    ys, xs = ys[keep], xs[keep]
    if not supported(ys):
        return None
    weights = 1 + Near_Weight * (ys - ys.min()) / (np.ptp(ys) + 1e-9)
    a, b = np.polyfit(ys - Target_Y, xs, 1, w=weights)
    if not np.all(np.isfinite([a, b])):
        return None
    if np.sqrt(np.mean((a * (ys - Target_Y) + b - xs) ** 2)) > Max_Fit_RMSE:
        return None
    return float(a), float(b - a * Target_Y)

#计算偏差（error）函数
def Computer_Error(Line , Middle_Line , Target_Y):  # 修改：使用固定前视行
    if Line is None:
        return None , 0.0

    A , B = Line
    Target_X = A*Target_Y + B
    error = int(round(Target_X - Middle_Line))  # 修改：四舍五入，避免浮点误差截断偏差
    Angle = float(np.degrees(np.arctan(A)))

    return error , Angle

#画图函数，在现有图像上画线，方便调试
def Draw_Line(Ima , Center_ys , Center_xs , Line , Middle_Line , Bottom_Y, Target_Y):
    #把ROI框，中心点，拟合线画图
    Ima_Show = Ima.copy()
    cv2.rectangle(Ima_Show,(0,ROI_UP),(Ima.shape[1]-1,Bottom_Y),(0,255,0),1)

    cv2.line(Ima_Show,(Middle_Line,ROI_UP),(Middle_Line,Bottom_Y),(255,255,255),1)

    for i in range(len(Center_ys)):                  #有效的中心点画绿点
        cv2.circle(Ima_Show,(int(round(Center_xs[i])),Center_ys[i]),2,(0,255,0),-1)
    # 画前视行；红线只画局部拟合区域，黄点为实际控制目标。
    cv2.line(Ima_Show, (0, Target_Y), (Ima.shape[1]-1, Target_Y), (0,255,255), 1)
    if Line is not None:
        A, B = Line
        half = int(Fit_Half_Window * Ima.shape[0] / 480.0)
        y_up = max(ROI_UP, Target_Y-half)
        y_down = min(Bottom_Y, Target_Y+half)
        cv2.line(Ima_Show, (int(A*y_up+B),y_up), (int(A*y_down+B),y_down), (0,0,255), 2)
        cv2.circle(Ima_Show, (int(round(A*Target_Y+B)),Target_Y), 5, (0,255,255), -1)
    return Ima_Show
#串口发送
# 沿用communication/serial_handler.py中的CarDo示范协议。
# 10字节：42 01 0A [速度float32小端4字节] [PWM uint16小端2字节] [前9字节和低8位]
# 不添加换行；实际CarDo固件必须支持此格式，当前未实现回执确认。
def Build_CarDo_Frame(speed, direction):
    if not math.isfinite(speed):
        raise ValueError("速度必须为有限数值")
    if type(direction) is not int or not 0 <= direction <= 65535:
        raise ValueError("PWM必须为uint16整数")
    body = bytes((0x42, 0x01, 0x0A)) + struct.pack('<fH', speed, direction)
    return body + bytes((sum(body) & 0xFF,))


def Send_Data_UART(Send):
    # 修改：E偏差/L/S仅为本程序内部指令；线上发送CarDo二进制帧。
    if ser is None:
        return True  # 图像调试模式，无串口输出。
    if Send == "S" or Send == "L":
        speed, direction = 0.0, int(STEER_CENTER)
        # 修改：没有可靠路面时立即发送零速度，避免继续沿用旧偏差行驶。
    elif Send.startswith("E"):
        deviation = int(Send[1:])
        speed = float(DRIVE_SPEED)
        direction = int(round(max(STEER_MIN, min(STEER_MAX,
                                   STEER_CENTER + STEER_KP * deviation))))
    else:
        raise ValueError("未知巡线指令")
    frame = Build_CarDo_Frame(speed, direction)
    try:
        written = ser.write(frame)
        if written != len(frame):
            raise OSError("串口帧未完整写入")
        return True  # 仅代表写入成功，不代表控制板已经执行。
    except (serial.SerialException, OSError) as exc:
        print("UART发送失败，退出巡线：", exc)
        return False




#===========================================================巡线主循环=================================================#

#====================丢线状态===============
Last_error = 0
Lost_Frame = 0
Previous_Center = None  # 修改：只缓存有效帧的底部中心，丢线立即清空

#退出或异常时统一释放资源。
try:
    #在资源保护范围内打开串口，并先发送零速度。
    ser = Open_UART()
    if not Send_Data_UART("S"):
        raise RuntimeError("UART初始停车帧发送失败")
    while True:
        #================================图像预处理================================
        ret , Ima = cap.read()
        if not ret or Ima is None:
            # 取帧失败退出，在finally中尝试发送零速度。
            print("摄像头取帧失败，停止巡线处理")
            break
        if not 0 <= ROI_UP < Ima.shape[0]:
            # 拒绝空ROI，避免后续图像处理报错。
            print("ROI_UP超出画面高度，请调整参数")
            break

        gray = cv2.cvtColor(Ima,cv2.COLOR_BGR2GRAY)   #转换为灰度图
        Imagin = gray[ROI_UP:, :]  # 修改：裁到实际底部，与Bottom_Y一致
        _,Ima_Bin = cv2.threshold(Imagin , Threshold , 225 , cv2.THRESH_BINARY_INV)
        # 灰度大于Threshold变为0，其余变为225，选取暗色区域。
        Ima_Bin = cv2.morphologyEx(Ima_Bin , cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        #开运算，清除孤立的噪点

        Width = Ima_Bin.shape[1]    #数一下Ima_Bin的形状属性，0表示数行数，1表示数列数
        Hight = Ima_Bin.shape[0]
        Middle_Line = Width // 2    #获取图像中线
        Bottom_Y = Ima.shape[0] -1  #车头行

        #========================================error计算========================
        # 前视行由ROI比例确定；上一有效帧帮助底部区段定位。
        Target_Y = int(round(ROI_UP + Lookahead_Ratio * (Bottom_Y - ROI_UP)))
        Center_xs, Center_ys = Find_Center(Ima_Bin, Previous_Center)
        Line = Center_Line(Center_ys, Center_xs, Target_Y, Ima.shape[0])
        error, Angle = Computer_Error(Line, Middle_Line, Target_Y)
        Previous_Center = Center_xs[0] if error is not None else None
        Ima_Show = Draw_Line(Ima, Center_ys, Center_xs, Line, Middle_Line, Bottom_Y, Target_Y)

        #=========================================丢线处理+串口发送==================
        if error is None:       #如果这一帧丢线
            Lost_Frame = Lost_Frame + 1
        else:                   #没有丢线
            Lost_Frame = 0
            Last_error = error

        if Lost_Frame == 0:
            Send = f"E{Last_error}"
        elif Lost_Frame <= Lost_Keep_Frame:
            Send = "L"
        else:
            Send = "S"

        # ----------------------------
        # |   下位机记得加通信看门狗   |
        # ----------------------------


        # 每帧发送一次；通信失败退出，不自动重连恢复运动。
        if not Send_Data_UART(Send):
            break

        cv2.imshow("YOU SEE",Ima_Show)
        cv2.imshow("THE CUT",Ima_Bin)
        #展示图像

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

finally:
    # q退出、断流或异常时尝试发送零速度；断线时无法保证到达。
    # CarDo固件还需配置通信超时停车；上位机退出逻辑不能替代它。
    try:
        Send_Data_UART("S")
    finally:
        try:
            if ser is not None:
                ser.close()
        finally:
            cap.release()
            cv2.destroyAllWindows()
