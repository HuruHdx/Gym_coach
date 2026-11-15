# 动作库清洗报告

- 总条数：5632
- 有效动作 `is_valid_exercise`：5631
- 主力动作 `coach_core`：280
- 主力已 LLM 精洗（stage2）：280
- 主力已有 aliases：280
- 主力已有 cues_zh：280
- 全库有 instructions_zh：1488
- 有 image_start：1314

## 枚举校验
- muscle 违规：0
- sub_region 违规：0
- movement_pattern 违规：0

## 主部位分布（全库）
- 腿: 1942
- 核心: 863
- 背: 784
- 臂: 714
- 肩: 684
- 胸: 473
- 全身: 172

## 主力动作主部位分布
- 腿: 137
- 核心: 57
- 臂: 27
- 背: 26
- 肩: 16
- 胸: 14
- 全身: 3

## 细分靶区 Top 30
- 臀部: 657
- 股四头肌(前侧): 648
- 上腹/腹直肌: 479
- 肩部整体: 461
- 中上背/背厚: 326
- 中胸: 311
- 肱三头肌: 298
- 肱二头肌: 263
- 小腿: 245
- 背阔肌/背宽: 229
- 腘绳肌(后侧): 214
- 下背/竖脊肌: 167
- 内收/外展肌: 161
- 腹斜肌(侧腹): 156
- 前臂: 153
- 全身爆发/HIIT: 141
- 核心抗旋/稳定: 138
- 下腹: 92
- 肩后束: 73
- 胸中缝/内侧: 64
- 斜方肌: 61
- 肩中束: 61
- 上胸: 59
- 肩前束: 47
- 心肺有氧: 47
- 肩袖/稳定: 42
- 下胸: 39

## 动作模式分布
- 膝主导(蹲): 1095
- 拉伸/灵活: 1015
- 肘屈伸(弯举/臂屈伸): 781
- 核心卷曲/稳定: 702
- 水平推: 471
- 水平拉: 355
- 垂直拉: 319
- 垂直推: 318
- 全身心肺/综合: 276
- 髋主导(铰链): 187
- 肩孤立(平举): 113

## 主力动作样例（前 40）
- [4604] PVC管早安式 / pvc good morning · 腿/腘绳肌(后侧) · aliases=['PVC早安', '早安式体前屈', 'Good Morning', '木棍早安']
- [4606] PVC管过头深蹲 / pvc overhead squat · 腿/股四头肌(前侧) · aliases=['PVC过顶深蹲', '木棍过头深蹲', 'Overhead Squat', '过顶深蹲']
- [3544] 上斜侧平板支撑 / bodyweight incline side plank · 核心/核心抗旋/稳定 · aliases=['上斜侧桥', '高位侧支撑', '斜身侧平板', 'Incline Side Plank', '跪姿侧平板']
- [0493] 上斜俯卧撑 / incline push-up · 胸/下胸 · aliases=['高台俯卧撑', '斜上俯卧撑', '扶高俯卧撑', 'Incline Push-Up']
- [3785] 上斜俯卧撑 / incline push-up (on box) · 胸/上胸 · aliases=['箱式上斜俯卧撑', '高位俯卧撑', '斜上俯卧撑', 'Incline Push-up']
- [3180] 上斜反向背伸 / incline reverse hyperextension · 腿/臀部 · aliases=['上斜反式背伸', '斜板反向挺身', '反向山羊挺身', 'Incline Reverse Hyperextension']
- [0314] 上斜哑铃卧推 / dumbbell incline bench press · 胸/上胸 · aliases=['上斜哑铃推胸', '上斜推胸', '上胸卧推', 'Incline DB Press', '上斜飞鸟推']
- [0047] 上斜杠铃卧推 / barbell incline bench press · 胸/上胸 · aliases=['上斜卧推', '上斜杠铃推胸', 'Incline Bench', '上斜推胸']
- [0279] 下斜俯卧撑 / decline push-up · 胸/上胸 · aliases=['脚抬高俯卧撑', '上胸俯卧撑', 'Decline Push-Up', '下斜撑']
- [8610] 中式平板支撑 / chinese plank · 核心/核心抗旋/稳定 · aliases=['平板支撑', '肘撑平板', '前臂支撑', 'Plank']
- [1510] 交叉后撤弓步蹲 / crossover reverse lunge · 腿/臀部 · aliases=['后交叉弓步蹲', '交叉后撤步蹲', '屈膝礼弓步', 'Curtsy Lunge']
- [5274] 仰卧屈膝卷腹 / lying tuck crunch · 核心/上腹/腹直肌 · aliases=['抱膝卷腹', '收膝卷腹', 'Tuck Crunch', '屈膝收腹']
- [1163] 仰卧抬腿 / lying leg raise · 核心/下腹 · aliases=['平躺抬腿', '仰卧举腿', 'Lying Leg Raise', '下腹抬腿']
- [4386] 伸腿平板支撑 / leg extension plank · 核心/核心抗旋/稳定 · aliases=['单腿伸展平板', '抬腿平板支撑', '单腿平板', 'Plank Leg Lift']
- [4788] 侧向分腿蹲 / side split squat · 腿/股四头肌(前侧) · aliases=['侧弓步蹲', '侧向深蹲', '侧跨步蹲', 'Side Split Squat']
- [8399] 侧向点地平板支撑 / side floor tap plank · 核心/核心抗旋/稳定 · aliases=['侧点地平板', '点地平板支撑', 'Side Tap Plank', '平板侧点地']
- [3958] 侧向移动平板支撑 / side step front plank · 核心/核心抗旋/稳定 · aliases=['侧步平板', '侧移平板支撑', '侧跨步平板', 'Side Step Plank']
- [1470] 侧平板支撑 / lateral side plank · 核心/核心抗旋/稳定 · aliases=['侧撑', '侧桥', '侧身平板', 'Side Plank']
- [2899] 侧平板支撑 / side plank (beginner) · 核心/核心抗旋/稳定 · aliases=['侧平板', '侧支撑', 'Side Plank', '初级侧桥', '侧桥']
- [6026] 侧平板支撑下拉 / side plank pull · 核心/核心抗旋/稳定 · aliases=['侧板下拉', '侧支撑拉背', 'Side Plank Pull', '侧平板划船']
- [4863] 侧平板支撑抬腿 / side plank leg lift · 核心/核心抗旋/稳定 · aliases=['侧板抬腿', '侧支撑抬腿', 'Side Plank Leg Lift', '侧平板举腿']
- [4811] 侧平板支撑标准式 / side plank v. 3 · 核心/核心抗旋/稳定 · aliases=['侧板支撑', '侧桥', 'Side Plank', '侧平板']
- [3264] 侧平板支撑直腿抬高 / side plank leg raise · 腿/内收/外展肌 · aliases=['侧板直腿抬高', '侧支撑举腿', 'Side Plank Leg Raise', '侧桥举腿']
- [4334] 侧平板支撑腹斜肌卷腹 / side plank oblique crunch · 核心/腹斜肌(侧腹) · aliases=['侧板卷腹', '侧支撑肘碰膝', 'Side Plank Crunch', '侧平板侧卷腹']
- [4991] 侧平板支撑转体 / side plank rotation · 核心/腹斜肌(侧腹) · aliases=['侧板转体', '侧支撑穿臂转体', 'Side Plank Rotation', '侧平板旋转']
- [1775] 侧平板支撑髋内收 / side plank hip adduction · 腿/内收/外展肌 · aliases=['侧板内收', '侧支撑夹腿', 'Side Plank Adduction', '侧平板髋内收']
- [9849] 侧平板蚌式开合 / side plank clamshell · 腿/内收/外展肌 · aliases=['侧板蚌式', '侧支撑蚌式', 'Side Plank Clamshell', '侧平板髋外展']
- [1899] 侧弓步内收肌拉伸 / side lunge adductor stretch · 腿/内收/外展肌 · aliases=['侧弓步拉伸', '内收肌拉伸', 'Side Lunge Adductor Stretch', '侧压腿拉伸']
- [5938] 俄罗斯转体劈砍 / russian twist chop · 核心/腹斜肌(侧腹) · aliases=['俄罗斯劈砍', '转体劈砍', 'Russian Twist Chop', '坐姿转体劈砍']
- [4832] 俯卧哑铃侧平举 / lying rear lateral raise · 肩/肩后束 · aliases=['俯卧后束飞鸟', '反向飞鸟', '俯身侧平举', 'Reverse Fly']
- [0662] 俯卧撑 / push-up · 胸/中胸 · aliases=['标准俯卧撑', '撑地俯卧撑', 'Push-up', '俯撑']
- [2961] 俯卧撑划船 / plank push up row · 背/中上背/背厚 · aliases=['叛徒划船', 'Renegade Row', '平板哑铃划船', '撑地单臂划船']
- [0027] 俯身杠铃划船 / barbell bent over row · 背/中上背/背厚 · aliases=['杠铃划船', '俯身划船', 'BOR', '俯身杠铃划船']
- [0471] 倒立俯卧撑 / handstand push-up · 臂/肱三头肌 · aliases=['靠墙倒立撑', '倒立推举', 'Handstand Push-Up', 'HSPU']
- [2133] 农夫行走 / farmers walk · 腿/核心抗旋/稳定 · aliases=['农夫走', '负重行走', '提铃行走', "Farmer's Walk", '手提箱行走']
- [4333] 凳上反向卷腹画圈 / bench reverse crunch circle · 核心/下腹 · aliases=['凳上反向卷腹', '反向画圈卷腹', '举腿画圆', 'Reverse Crunch Circle', '下腹绕圈']
- [0781] 分腿蹲 / split squat · 腿/股四头肌(前侧) · aliases=['原地分腿蹲', '静态分腿蹲', 'Split Squat', '前后分腿蹲']
- [2368] 分腿蹲 / split squats · 腿/股四头肌(前侧) · aliases=['前跨分腿蹲', '迈步分腿蹲', 'Split Squats', '前后脚蹲']
- [3750] 前平板支撑侧跳 / front plank side hop · 核心/核心抗旋/稳定 · aliases=['平板侧跳', '侧向跳平板', '平板支撑侧向跳', 'Plank Side Hop', '侧跳平板撑']
- [3814] 前平板支撑点脚 / front plank toe tap · 核心/核心抗旋/稳定 · aliases=['平板点脚', '平板支撑点趾', '点脚平板', 'Plank Toe Tap', '侧点脚平板']
