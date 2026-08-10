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
        {"id": "754f3fae6a3b4d8496ab3cfb9a411140", "name": "风吟 - 纪录片解说", "style": "成熟女声 · 纪录片 · 平静"},
        {"id": "b255ca2902514f69bc22243436a94e4f", "name": "曼波", "style": "年轻女声 · 教学 · 明亮活力"},
    ])
    volcApiKey: str = Field(default="")
    volcSpeakerId: str = Field(default="")
    volcResourceId: str = Field(default="seed-icl-2.0")
    volcVoiceName: str = Field(default="KV 音色")
    # 火山云 V3 speech_rate: -50 = 0.5 倍速，100 = 2.0 倍速。
    volcSpeechRate: int = Field(default=0, ge=-50, le=100)
    customApiUrl: str = Field(default="")
    customApiKey: str = Field(default="")
    customVoice: str = Field(default="")
    customSpeed: float = Field(default=0.0)
    edgeVoice: str = Field(default="zh-CN-XiaoxiaoNeural")
    edgeRate: float = Field(default=0.0)
    edgePitch: float = Field(default=0.0)
