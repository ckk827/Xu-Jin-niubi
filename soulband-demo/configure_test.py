"""Prepare the persistent acceptance sandbox without resetting existing records."""
import storage as db


def main():
    def configure(state):
        state.update(mode="ollama", model="qwen2.5:7b")
        state["analysis"] = None
        state["environment"] = "独立验收测试库 · 保留重启前记录"
        db.trace(state, "真实模型测试环境已准备", "不覆盖原有演示数据库；本库重启不清空")
    db.mutate(configure)
    print("Acceptance database:", db.DB_PATH)


if __name__ == "__main__": main()
