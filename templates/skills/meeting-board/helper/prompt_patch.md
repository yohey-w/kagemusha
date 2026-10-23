## 出力（差分）

この依頼では、上の「出力」の代わりに、次の形で「前回から変わったところだけ」を返す。JSON だけを返す。前置き・説明・コードフェンスは書かない。

{
  "mode": "patch",
  "topics": [
    {"title": "話題名", "id": "t3", "headline": "いまの結論か状態を1行で", "current": true, "points": [{"speaker": "話者名", "text": "言ったこと"}], "decisions": [], "todos": [{"who": "誰が", "what": "何を", "when": "いつまで", "ref": ""}], "numbers": []}
  ],
  "current_id": "t3",
  "checklist": [{"id": "q2", "state": "done", "owner": "", "evidence": "根拠"}],
  "open_questions": ["まだ答えが出ていない問い"],
  "next_action": {"text": "次に言う・聞く一言", "reason": "なぜいまか", "ref": "q3"},
  "warnings": [],
  "status": "進み具合を1行で",
  "conflicts": [],
  "cards": []
}

## 差分の決まり

- 【字幕】は前回より後の分だけ（手前に少し重ねてある）。【前回までの整理】が、それより前の話のすべて
- topics には、変わった話題と新しい話題だけを書く。既にある話題は id をそのまま使い、中身（points・decisions・todos・numbers）はその話題の分を全部書く。新しい話題は id を "" にする。変わっていない話題は書かない（書かなかった話題は前回のまま残る）
- 【前回までの整理】で title・id・headline だけが渡されている話題は、中身を省いてある。その話題に続きが出たときは、新しく分かったことだけを書く（前の中身はヘルパーが残す）
- current_id は、いま話している話題の id（新しい話題なら ""。その話題の current を true にする）
- checklist は、状態・担当・根拠が変わった項目だけ。変わっていない項目は書かない
- conflicts は、新しく出たもの・変わったものだけ
- open_questions・next_action・warnings・status・cards は、いつも「いまの全部」を書く（無ければ [] や ""）
- それ以外の決まり（1〜18）は上と同じ
