/** 内测/开发者「测试反馈」开关：开了才在教练气泡下显示点赞踩与轨迹号。 */
export const TEST_FEEDBACK_KEY = "gym_coach_test_feedback";
export const TEST_FEEDBACK_EVENT = "gym_coach_test_feedback";

export function isTestFeedbackEnabled(): boolean {
  try {
    return localStorage.getItem(TEST_FEEDBACK_KEY) === "1";
  } catch {
    return false;
  }
}

export function setTestFeedbackEnabled(on: boolean): void {
  try {
    localStorage.setItem(TEST_FEEDBACK_KEY, on ? "1" : "0");
  } catch {
    /* ignore quota / private mode */
  }
  window.dispatchEvent(new Event(TEST_FEEDBACK_EVENT));
}
