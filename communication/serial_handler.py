# ============================================================
#  串口通信 — CarDo 智控板协议 (示范版)
# ------------------------------------------------------------
#  协议格式（变长帧）:
#    ┌──────┬──────┬────────┬────────────┬───────┐
#    │ Head │ Addr │ Length │  D0 ~ D5   │ Check │
#    │ 0x42 │ 1B   │  1B    │  数据位     │  1B   │
#    └──────┴──────┴────────┴────────────┴───────┘
#    Check = (Head + Addr + Length + 所有数据位) 的低 8 位
#    波特率 115200
# ============================================================
import serial
import struct


HEAD = 0x42            # 固定帧头


def build_frame(addr, data_bytes):
    """
    把地址 + 数据打包成一条完整的协议帧。
    addr:       功能地址，比如 0x01=速度方向
    data_bytes: 数据位（bytes），比如速度4字节+方向2字节
    返回: 完整帧的 bytes
    """
    length = 3 + len(data_bytes) + 1        # Head+Addr+Length 3字节 + 数据 + Check 1字节
    frame = bytearray()
    frame.append(HEAD)                      # 帧头
    frame.append(addr)                      # 地址
    frame.append(length)                    # 帧长度
    frame.extend(data_bytes)                # 数据位

    # 校验和 = 前面所有字节之和，取低 8 位
    check = (HEAD + addr + length + sum(data_bytes)) & 0xFF
    frame.append(check)
    return bytes(frame)


def build_speed_dir(speed, direction):
    """
    打包"速度 + 方向"帧（地址 0x01）
    speed:     float，闭环单位 m/s (-10.0~10.0)，开环是占空比 %
    direction: int，舵机 pwm 500~2500，1500 通常是中值(直行)
    """
    # 速度用 4 字节 float（小端），方向用 2 字节无符号整数（小端）
    data = struct.pack('<f', speed) + struct.pack('<H', direction)
    return build_frame(0x01, data)


# ==================== 示范：打印一帧看看长什么样 ====================
if __name__ == "__main__":
    # 例：速度 1.5 m/s，方向 1500(直行)
    frame = build_speed_dir(1.5, 1500)
    print("速度1.5m/s 方向1500 的帧:")
    print(" ".join(f"{b:02X}" for b in frame))    # 十六进制打印
    print(f"共 {len(frame)} 字节")

    # 例：停车（速度0，方向中值）
    frame2 = build_speed_dir(0.0, 1500)
    print("\n停车帧:")
    print(" ".join(f"{b:02X}" for b in frame2))
