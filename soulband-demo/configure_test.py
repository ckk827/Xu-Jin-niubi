"""Prepare the persistent acceptance sandbox without resetting existing records."""
import storage as db


def main():
    def configure(state):
        # Older launchers forced Ollama on every boot. Ask once before using it.
        if not state.get("model_configured"):
            state.update(mode="unconfigured", model="", analysis=None)
        state["environment"] = "独立验收测试库 · 保留重启前记录"
        db.trace(state, "宿主环境已准备", "模型由用户选择；本库重启不清空")
    db.mutate(configure)
    print("Acceptance database:", db.DB_PATH)


if __name__ == "__main__": main()
