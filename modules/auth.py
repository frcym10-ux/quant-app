"""
modules/auth.py
Streamlit公開時の任意パスワードゲート（多層防御）

`APP_PASSWORD` が st.secrets または環境変数に設定されている場合のみ、
各ページでパスワード入力を要求する。未設定なら何もしない（no-op）ため、
ローカル開発・CI・静的レポート生成・GitHub Actionsには一切影響しない。

Streamlit Community Cloud の「閲覧者をメールで限定」設定（Google/GitHubログイン）と
併用すると、SSO＋アプリ内パスワードの二重防御になる。
Streamlitはマルチページでも各ページが独立実行されるため、ページ単位でこのゲートを呼ぶ。
"""
from __future__ import annotations

import hmac
import os

SESSION_KEY = "_authenticated"


def _expected_password() -> str:
    """設定されたアプリパスワードを返す（st.secrets優先、なければ環境変数）"""
    try:
        import streamlit as st
        # secrets.toml が無い環境では st.secrets アクセスが例外になり得るため握りつぶす
        if "APP_PASSWORD" in st.secrets:
            return str(st.secrets["APP_PASSWORD"])
    except Exception:
        pass
    return os.getenv("APP_PASSWORD", "")


def require_auth() -> None:
    """パスワードが設定されていれば認証を要求する。未設定なら何もしない"""
    import streamlit as st

    password = _expected_password()
    if not password:
        return  # パスワード未設定 → 認証なしで通す（ローカル開発など）

    if st.session_state.get(SESSION_KEY):
        return  # 認証済み

    st.title("🔒 ログイン")
    st.caption("このアプリは限定公開です。パスワードを入力してください。")
    entered = st.text_input("パスワード", type="password")
    if entered:
        if hmac.compare_digest(entered, password):
            st.session_state[SESSION_KEY] = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()  # 認証が通るまで以降の描画を止める
