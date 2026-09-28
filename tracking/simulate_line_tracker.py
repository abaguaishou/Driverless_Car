"""巡线视觉回归仿真：不打开摄像头，不打开串口，不模拟车辆动力学。

在tracking目录执行：python simulate_line_tracker.py
显示逐张测试画面：python simulate_line_tracker.py --show
输出到 simulation_output：HTML报告、JSON结果、输入和处理图。
"""
import argparse
import ast
import hashlib
import html
import json
from pathlib import Path

import cv2
import numpy as np


def load_tracker(path):
    """仅加载原文件常量、算法函数和原样预处理语句，隔离硬件副作用。"""
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(path))
    names = {"Find_Center", "Center_Line", "Computer_Error", "Draw_Line"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            try:
                ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
    ns = {"np": np, "cv2": cv2}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    if not names.issubset(ns):
        raise RuntimeError("巡线函数接口已变化，请更新仿真适配器")
    # 原样复用主循环中的灰度转换、裁剪、阈值和开运算。
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.While)]
    processing = []
    for loop in loops:
        active = False
        for n in loop.body:
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "gray" for t in n.targets):
                active = True
            if active:
                processing.append(n)
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "morphologyEx":
                    active = False
                    break
        if processing:
            break
    if len(processing) != 4 or not all(isinstance(n, ast.Assign) for n in processing):
        raise RuntimeError("预处理结构已变化，请核对仿真适配器；不会运行主循环")
    return ns, compile(ast.Module(body=processing, type_ignores=[]), str(path), "exec"), hashlib.sha256(text.encode()).hexdigest()


def scene(kind, offset=0, width=640, height=480):
    """生成已知道路几何；测试阈值固定，不按算法结果改变预期。"""
    frame = np.full((height, width, 3), 220, np.uint8)
    truth = []
    for y in range(height):
        t = (height - 1 - y) / (height - 1)
        bend = 140 * t*t if kind == "curve" else 65*np.sin(t*np.pi*2) if kind == "s_curve" else 0
        center = width/2 + (offset+bend)*width/640
        half = (48+65*y/(height-1))*width/640
        truth.append(center)
        left, right = round(center-half), round(center+half)
        cv2.line(frame, (left, y), (right, y), (50, 50, 50), 1)
        cv2.line(frame, (left-2, y), (left+2, y), (255, 255, 255), 1)
        cv2.line(frame, (right-2, y), (right+2, y), (255, 255, 255), 1)
    if kind == "distractor":
        cv2.rectangle(frame, (15, 240), (90, height-1), (50,50,50), -1)
    elif kind == "noise":
        rng = np.random.default_rng(2026)
        frame = np.clip(frame.astype(float)+rng.normal(0,7,frame.shape),0,255).astype(np.uint8)
    elif kind == "blank":
        frame[:] = 220
    elif kind == "dark":
        frame[:] = 50
    elif kind == "gap":
        frame[height-90:height-60] = 220
    elif kind == "ambiguous":
        frame[:] = 220
        frame[:, 190:261] = 50
        frame[:, 380:451] = 50
    return frame, np.array(truth)


def process(ns, preprocessing, frame, seed=None):
    h,w = frame.shape[:2]
    if not 0 <= ns["ROI_UP"] < h:
        raise ValueError("ROI_UP超出模拟画面高度")
    env = dict(ns, Ima=frame)
    exec(preprocessing, env)
    mask = env["Ima_Bin"]
    target = round(ns["ROI_UP"]+ns["Lookahead_Ratio"]*(h-1-ns["ROI_UP"]))
    xs,ys = ns["Find_Center"](mask,seed)
    line = ns["Center_Line"](ys,xs,target,h)
    error, angle = ns["Computer_Error"](line,w//2,target)
    drawing = ns["Draw_Line"](frame,ys,xs,line,w//2,h-1,target)
    return error,angle,target,drawing,mask,(xs[0] if error is not None else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracker", type=Path, default=Path(__file__).with_name("line_tracker.py"))
    parser.add_argument("--output", type=Path, default=Path(__file__).parent/"simulation_output")
    parser.add_argument("--show", action="store_true", help="显示画面：任意键下一张，Q停止预览（仍完成测试）")
    args = parser.parse_args()
    ns, preprocessing, digest = load_tracker(args.tracker)
    args.output.mkdir(parents=True,exist_ok=True)
    # 每项预期独立于算法输出：正常场景偏差误差<=8px，失效场景必须报丢线。
    cases = [
        ("straight", "居中直线", "straight",0,False),
        ("left", "道路左移", "straight",-90,False),
        ("right", "道路右移", "straight",90,False),
        ("curve", "缓右弯", "curve",0,False),
        ("s_curve", "S弯", "s_curve",0,False),
        ("distractor", "左侧独立暗色干扰", "distractor",0,False),
        ("noise", "固定种子噪声", "noise",0,False),
        ("blank", "无道路", "blank",0,True),
        ("dark", "整幅暗图", "dark",0,True),
        ("gap", "大片路面缺失", "gap",0,True),
        ("ambiguous", "两个等距候选", "ambiguous",0,True),
        ("clipped", "道路边界出画面", "straight",290,True),
    ]
    results=[]
    show=args.show
    try:
        for key,label,kind,offset,lost in cases:
            frame,truth=scene(kind,offset)
            error,angle,target,drawing,mask,_=process(ns,preprocessing,frame)
            expected=None if lost else float(truth[target]-frame.shape[1]//2)
            difference=None if expected is None or error is None else abs(error-expected)
            passed=(error is None) if lost else (difference is not None and difference<=8)
            binary=np.zeros_like(frame)
            binary[ns["ROI_UP"]:]=cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR)
            pair=np.hstack([drawing,binary])
            status="PASS" if passed else "FAIL"
            cv2.putText(pair,f"{key}: {status}  error={error}  truth={expected}",(10,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,180,255),2)
            if not cv2.imwrite(str(args.output/(key+".png")),pair):
                raise IOError("无法保存处理图")
            cv2.imwrite(str(args.output/(key+"_input.png")),frame)
            result=dict(name=key,label=label,passed=passed,error=error,expected=expected,absolute_error=difference,target_y=target,image=key+".png")
            results.append(result)
            print(f"{status:4} {key:12} error={error}, expected={expected}")
            if show:
                cv2.imshow("Simulation: any key next, Q stop preview",pair)
                if cv2.waitKey(0)&255==ord('q'):
                    show=False
        # 连续帧：横移→丢线→重新捕获，验证上一帧种子和清空行为。
        seed=None
        temporal=[]
        for offset in range(-60,61,10):
            frame,_=scene("straight",offset)
            error,_,_,_,_,seed=process(ns,preprocessing,frame,seed)
            temporal.append(error is not None and abs(error-offset)<=2)
        frame,_=scene("blank")
        error,_,_,_,_,seed=process(ns,preprocessing,frame,seed)
        temporal.append(error is None and seed is None)
        frame,_=scene("straight",-80)
        error,_,_,_,_,seed=process(ns,preprocessing,frame,seed)
        temporal.append(error is not None and abs(error+80)<=2)
        results.append(dict(name="temporal",label="连续帧移动、丢线及恢复",passed=all(temporal),frames=len(temporal)))
    finally:
        if args.show:
            cv2.destroyAllWindows()
    passed=sum(r["passed"] for r in results)
    report=dict(tracker=str(args.tracker.resolve()),source_sha256=digest,passed=passed,total=len(results),results=results)
    (args.output/"results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    cards=[]
    for r in results:
        cards.append('<section><h2>'+html.escape(r['label'])+' — '+('通过' if r['passed'] else '失败')+'</h2>'
            +('<p>算法偏差：'+str(r.get('error'))+'；真实偏差：'+str(r.get('expected'))+'</p><img src="'+r['image']+'" alt="输入标注及二值图">' if 'image' in r else '<p>共15帧，检查移动、丢线与恢复。</p>')+'</section>')
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>巡线仿真报告</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:0 16px;background:#f5f6f8;color:#18212d}section{background:white;padding:18px;margin:16px 0;border-radius:12px}img{width:100%;height:auto}h2{font-size:19px}</style><h1>巡线视觉仿真：'+str(passed)+' / '+str(len(results))+' 通过</h1><p>左：真实巡线函数标注；右：真实预处理输出。None表示丢线。仅验证合成图像，不代表实车完成率，不模拟动力学，不连接摄像头或串口。</p>'+''.join(cards)+'</html>'
    (args.output/"report.html").write_text(page,encoding="utf-8")
    print(f"Result: {passed}/{len(results)}; report: {args.output/'report.html'}")
    return 0 if passed==len(results) else 1


if __name__=="__main__":
    raise SystemExit(main())
