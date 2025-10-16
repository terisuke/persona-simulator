"""
類似投稿検索モジュール
sentence-transformersを使用してトピックに関連する投稿を抽出
"""

import logging
from typing import List, Dict
import numpy as np
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)


class SimilaritySearcher:
    """投稿の類似検索を行うクラス"""
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        Args:
            model_name: 使用するSentence Transformersモデル
        """
        logger.info(f"類似検索モデルをロード中: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.info("モデルロード完了")
    
    def find_relevant_posts(
        self, 
        topic: str, 
        posts: List[Dict], 
        top_k: int = 3
    ) -> List[Dict]:
        """
        トピックに関連する投稿を検索
        
        Args:
            topic: 検索トピック
            posts: 投稿リスト
            top_k: 上位K件を返す
            
        Returns:
            関連度が高い投稿リスト（スコア付き）
        """
        if not posts:
            logger.warning("投稿が空のため、検索をスキップ")
            return []
        
        logger.info(f"類似検索開始: トピック='{topic}', 投稿数={len(posts)}, top_k={top_k}")
        
        try:
            # トピックのエンベディング
            topic_embedding = self.model.encode(topic, convert_to_tensor=True)
            
            # 投稿のエンベディング
            post_texts = [post["text"] for post in posts]
            post_embeddings = self.model.encode(post_texts, convert_to_tensor=True)
            
            # コサイン類似度計算
            similarities = util.cos_sim(topic_embedding, post_embeddings)[0]
            
            # スコアでソート
            top_indices = np.argsort(-similarities.cpu().numpy())[:top_k]
            
            relevant_posts = []
            for idx in top_indices:
                post = posts[idx].copy()
                post["similarity_score"] = float(similarities[idx])
                relevant_posts.append(post)
            
            logger.info(f"類似検索完了: {len(relevant_posts)}件抽出")
            for i, post in enumerate(relevant_posts):
                logger.debug(f"  [{i+1}] スコア={post['similarity_score']:.3f}: {post['text'][:50]}...")
            
            return relevant_posts
            
        except Exception as e:
            logger.error(f"類似検索エラー: {str(e)}")
            return posts[:top_k]  # フォールバック: 最初のK件を返す
    
    def cluster_posts(self, posts: List[Dict], n_clusters: int = 5) -> Dict[int, List[Dict]]:
        """
        投稿をクラスタリング（将来の拡張用）
        
        Args:
            posts: 投稿リスト
            n_clusters: クラスタ数
            
        Returns:
            クラスタID -> 投稿リストの辞書
        """
        if not posts or len(posts) < n_clusters:
            logger.warning("投稿数が不足、クラスタリングをスキップ")
            return {0: posts}
        
        logger.info(f"クラスタリング開始: {len(posts)}件 -> {n_clusters}クラスタ")
        
        try:
            from sklearn.cluster import KMeans
            
            # エンベディング生成
            post_texts = [post["text"] for post in posts]
            embeddings = self.model.encode(post_texts)
            
            # K-meansクラスタリング
            kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            labels = kmeans.fit_predict(embeddings)
            
            # クラスタごとにグループ化
            clusters = {}
            for i, label in enumerate(labels):
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(posts[i])
            
            logger.info(f"クラスタリング完了: {len(clusters)}クラスタ生成")
            return clusters
            
        except Exception as e:
            logger.error(f"クラスタリングエラー: {str(e)}")
            return {0: posts}

