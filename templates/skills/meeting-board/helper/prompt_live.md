## 出力（会議中の短い版）

この依頼では、上の「出力」の代わりに、会議中の画面に出す分だけを返す。話題（topics）と open_questions は書かない（ヘルパーが前回のまま残し、数分おきに別の依頼でまとめ直す）。JSON だけを返す。前置き・説明・コードフェンスは書かない。

{
  "mode": "live",
  "current_id": "t3",
  "checklist": [{"id": "q2", "state": "done", "owner": "", "evidence": "根拠"}],
  "next_action": {"text": "次に言う・聞く一言", "reason": "なぜいまか", "ref": "q3"},
  "warnings": [],
  "status": "進み具合を1行で",
  "conflicts": [],
  "closing_candidates": [],
  "cards": []
}

## 短い版の決まり

- 【字幕】は前回より後の分だけ（手前に少し重ねてある）。それより前の話は、【前回までの整理】の話題の見出し（title・headline）と、checklist の根拠（evidence）で分かる
- current_id は、いま話している話題の id。【前回までの整理】のどの話題にも当たらない新しい話なら ""
- checklist は、状態・担当・根拠が変わった項目だけ。変わっていない項目は書かない
- conflicts は、新しく出たもの・変わったものだけ
- next_action・warnings・status・cards・closing_candidates は、いつも「いまの全部」を書く（無ければ [] や ""）
- それ以外の決まり（12〜19）は上と同じ。話題の決まり（1〜11）はこの依頼では使わない
