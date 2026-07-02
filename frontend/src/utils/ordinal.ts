// 轮次中文序数：第一次 / 第二次 …（超过十用阿拉伯数字）
const CN_NUM = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
export const cnOrdinal = (n: number) => (n >= 0 && n <= 10 ? CN_NUM[n] : String(n))
