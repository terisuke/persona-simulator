"""
議論UI管理モジュール
チャット風UIとターン制議論を提供
"""

import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional
import logging
import html

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
        """チャット風にメッセージを表示"""
        avatar = self.assign_avatar(message.account)
        bg_color = self.MESSAGE_COLORS.get(message.message_type, "#f5f5f5")
        
        # メッセージ内容をHTMLエスケープ
        escaped_content = html.escape(message.content)
        escaped_account = html.escape(message.account)
        
        # 返信先の表示
        reply_html = ""
        if message.reply_to:
            escaped_reply_to = html.escape(message.reply_to)
            reply_html = f"""
            <div style="font-size: 0.8em; color: #666; margin-bottom: 5px;">
                💬 @{escaped_reply_to} への返信
            </div>
            """
        
        # メッセージタイプのバッジ
        badge_html = ""
        if message.message_type == "reply":
            badge_html = '<span style="background: #9c27b0; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.7em; margin-left: 5px;">返信</span>'
        elif message.message_type == "rebuttal":
            badge_html = '<span style="background: #ff9800; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.7em; margin-left: 5px;">反論</span>'
        
        if align_right:
            # 右寄せ（自分のメッセージ風）
            html_content = f"""
            <div style="display: flex; justify-content: flex-end; margin: 15px 0;">
                <div style="max-width: 70%; background: {bg_color}; padding: 12px 16px; border-radius: 18px 18px 5px 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                    {reply_html}
                    <div style="font-weight: bold; color: #1976d2; margin-bottom: 5px;">
                        {avatar} @{escaped_account} {badge_html}
                    </div>
                    <div style="color: #424242; line-height: 1.5;">
                        {escaped_content}
                    </div>
                    <div style="text-align: right; font-size: 0.75em; color: #757575; margin-top: 5px;">
                        {message.timestamp}
                    </div>
                </div>
            </div>
            """
        else:
            # 左寄せ（相手のメッセージ風）
            html_content = f"""
            <div style="display: flex; justify-content: flex-start; margin: 15px 0;">
                <div style="max-width: 70%; background: {bg_color}; padding: 12px 16px; border-radius: 18px 18px 18px 5px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                    {reply_html}
                    <div style="font-weight: bold; color: #1976d2; margin-bottom: 5px;">
                        {avatar} @{escaped_account} {badge_html}
                    </div>
                    <div style="color: #424242; line-height: 1.5;">
                        {escaped_content}
                    </div>
                    <div style="text-align: left; font-size: 0.75em; color: #757575; margin-top: 5px;">
                        {message.timestamp}
                    </div>
                </div>
            </div>
            """
        
        st.markdown(html_content, unsafe_allow_html=True)
    
    def render_round_header(self, round_num: int):
        """ラウンドヘッダーを表示"""
        if round_num == 0:
            title = "📢 初回意見"
        else:
            title = f"🔄 ラウンド {round_num} - 反論・応答"
        
        st.markdown(f"""
        <div style="text-align: center; margin: 30px 0 20px 0; padding: 15px; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h3 style="color: white; margin: 0; font-size: 1.3em;">
                {title}
            </h3>
        </div>
        """, unsafe_allow_html=True)
    
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
                st.markdown(f"""
                <div style="text-align: center; padding: 10px; background: #f5f5f5; border-radius: 10px; margin: 5px;">
                    <div style="font-size: 2em;">{avatar}</div>
                    <div style="font-weight: bold; margin-top: 5px;">@{account}</div>
                </div>
                """, unsafe_allow_html=True)
    
    def get_current_round(self) -> int:
        """現在のラウンド番号を取得"""
        return st.session_state['debate_round']
    
    def get_all_accounts(self) -> List[str]:
        """参加している全アカウントを取得"""
        messages = self.get_messages()
        accounts = list(set([m.account for m in messages]))
        return sorted(accounts)

