"""
議論UI管理モジュール
チャット風UIとターン制議論を提供
"""

import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class DebateMessage:
    """議論メッセージクラス"""
    
    def __init__(
        self,
        account: str,
        name: str,
        content: str,
        round_num: int,
        timestamp: str = None,
        reply_to: Optional[str] = None,
        message_type: str = "initial"  # initial, reply, rebuttal
    ):
        self.account = account
        self.name = name
        self.content = content
        self.round_num = round_num
        self.timestamp = timestamp or datetime.now().strftime("%H:%M")
        self.reply_to = reply_to
        self.message_type = message_type


class DebateUI:
    """議論UI管理クラス"""
    
    # アバター絵文字（ランダムに割り当て）
    AVATARS = ["🧑", "👨", "👩", "🧔", "👨‍💼", "👩‍💼", "🧑‍💻", "👨‍🔬", "👩‍🔬", "🧑‍🎓"]
    
    # メッセージタイプごとの色
    MESSAGE_COLORS = {
        "initial": "#e3f2fd",    # 水色
        "reply": "#f3e5f5",      # 紫
        "rebuttal": "#fff3e0"    # オレンジ
    }
    
    def __init__(self):
        """初期化"""
        if 'debate_messages' not in st.session_state:
            st.session_state['debate_messages'] = []
        if 'debate_round' not in st.session_state:
            st.session_state['debate_round'] = 0
        if 'account_avatars' not in st.session_state:
            st.session_state['account_avatars'] = {}
    
    def assign_avatar(self, account: str) -> str:
        """アカウントにアバターを割り当て"""
        if account not in st.session_state['account_avatars']:
            # まだ割り当てられていないアバターから選択
            used_avatars = set(st.session_state['account_avatars'].values())
            available = [a for a in self.AVATARS if a not in used_avatars]
            if available:
                st.session_state['account_avatars'][account] = available[0]
            else:
                # 全部使い切ったら最初から
                st.session_state['account_avatars'][account] = self.AVATARS[0]
        return st.session_state['account_avatars'][account]
    
    def add_message(
        self,
        account: str,
        name: str,
        content: str,
        reply_to: Optional[str] = None,
        message_type: str = "initial"
    ):
        """メッセージを追加"""
        current_round = st.session_state['debate_round']
        message = DebateMessage(
            account=account,
            name=name,
            content=content,
            round_num=current_round,
            reply_to=reply_to,
            message_type=message_type
        )
        st.session_state['debate_messages'].append(message)
        logger.info(f"メッセージ追加: {account} (ラウンド{current_round})")
    
    def get_messages(self, round_num: Optional[int] = None) -> List[DebateMessage]:
        """メッセージを取得"""
        messages = st.session_state['debate_messages']
        if round_num is not None:
            messages = [m for m in messages if m.round_num == round_num]
        return messages
    
    def increment_round(self):
        """ラウンドを進める"""
        st.session_state['debate_round'] += 1
        logger.info(f"ラウンド{st.session_state['debate_round']}に進行")
    
    def clear_debate(self):
        """議論をクリア"""
        st.session_state['debate_messages'] = []
        st.session_state['debate_round'] = 0
        logger.info("議論をクリアしました")
    
    def render_message(self, message: DebateMessage, align_right: bool = False):
        """チャット風にメッセージを表示（Streamlit標準コンポーネント使用）"""
        avatar = self.assign_avatar(message.account)
        
        # メッセージタイプのバッジ
        badge = ""
        if message.message_type == "reply":
            badge = "💬 返信"
        elif message.message_type == "rebuttal":
            badge = "🔥 反論"
        
        # 返信先の表示
        if message.reply_to:
            st.caption(f"💬 @{message.reply_to} への返信")
        
        # メッセージヘッダー
        header = f"{avatar} **@{message.account}**"
        if badge:
            header += f" `{badge}`"
        header += f" - {message.timestamp}"
        
        # メッセージを表示（Streamlitの標準コンポーネント）
        if message.message_type == "initial":
            with st.container():
                st.markdown(header)
                st.info(message.content)
        elif message.message_type == "reply":
            with st.container():
                st.markdown(header)
                st.success(message.content)
        elif message.message_type == "rebuttal":
            with st.container():
                st.markdown(header)
                st.warning(message.content)
        else:
            with st.container():
                st.markdown(header)
                st.info(message.content)
    
    def render_round_header(self, round_num: int):
        """ラウンドヘッダーを表示"""
        if round_num == 0:
            st.subheader("📢 初回意見")
        else:
            st.subheader(f"🔄 ラウンド {round_num} - 反論・応答")
    
    def render_debate_timeline(self):
        """議論全体をタイムライン形式で表示"""
        messages = self.get_messages()
        
        if not messages:
            st.info("💬 まだ議論が始まっていません。「🚀 議論を開始」ボタンをクリックしてください。")
            return
        
        # ラウンド別にグループ化
        rounds = {}
        for msg in messages:
            if msg.round_num not in rounds:
                rounds[msg.round_num] = []
            rounds[msg.round_num].append(msg)
        
        # ラウンドごとに表示
        for round_num in sorted(rounds.keys()):
            self.render_round_header(round_num)
            
            round_messages = rounds[round_num]
            for i, msg in enumerate(round_messages):
                # 交互に左右に配置（視覚的な変化）
                align_right = (i % 2 == 1)
                self.render_message(msg, align_right=align_right)
            
            # ラウンド区切り
            if round_num < max(rounds.keys()):
                st.markdown("---")
    
    def render_participant_list(self, accounts: List[str]):
        """参加者リストを表示"""
        st.markdown("### 👥 参加者")
        
        cols = st.columns(len(accounts))
        for i, account in enumerate(accounts):
            with cols[i]:
                avatar = self.assign_avatar(account)
                # Streamlit標準コンポーネントを使用
                st.markdown(f"<div style='text-align: center; font-size: 2.5em;'>{avatar}</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='text-align: center; font-weight: bold;'>@{account}</div>", unsafe_allow_html=True)
    
    def get_current_round(self) -> int:
        """現在のラウンド番号を取得"""
        return st.session_state['debate_round']
    
    def get_all_accounts(self) -> List[str]:
        """参加している全アカウントを取得"""
        messages = self.get_messages()
        accounts = list(set([m.account for m in messages]))
        return sorted(accounts)

