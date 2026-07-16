from pydantic import BaseModel, Field


class TtsSettings(BaseModel):
    engine: str = Field(default="edge")
    manboApiUrl: str = Field(default="https://api.milorapart.top/apis/mbAIscvip")
    manboApiKey: str = Field(default="")
    fishApiKey: str = Field(default="")
    fishReferenceId: str = Field(default="754f3fae6a3b4d8496ab3cfb9a411140")
    fishModel: str = Field(default="s2.1-pro-free")
    fishSpeed: float = Field(default=1.0)
    fishVoicePresets: list = Field(default_factory=lambda: [
        {"id": "754f3fae6a3b4d8496ab3cfb9a411140", "name": "椋庡悷鈥斺€旂邯褰曠墖瑙ｈ", "style": "鑰佸勾濂冲０ 路 绾綍鐗?路 骞抽潤"},
        {"id": "b255ca2902514f69bc22243436a94e4f", "name": "鏇兼尝", "style": "骞磋交濂冲０ 路 鏁欏 路 鏄庝寒娲诲姏"},
    ])
    customApiUrl: str = Field(default="")
    customApiKey: str = Field(default="")
    customVoice: str = Field(default="")
    customSpeed: float = Field(default=0.0)
    edgeVoice: str = Field(default="zh-CN-XiaoxiaoNeural")
    edgeRate: float = Field(default=0.0)
    edgePitch: float = Field(default=0.0)
