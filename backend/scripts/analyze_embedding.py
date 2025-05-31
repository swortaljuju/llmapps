from dotenv import load_dotenv, find_dotenv
import sys
import os

# Load environment variables from .env
load_dotenv(
    find_dotenv(filename=".env.local"), override=True
)  # Load local environment variables if available


# Add the parent directory to sys.path so that we can import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib.pyplot as plt
import seaborn as sns
from db.db import get_sql_db
from db.models.newssummary import NewsEntry
from datetime import date
import numpy as np
from sklearn.metrics import pairwise_distances
from sklearn.manifold import TSNE

def __get_embedding_data(start_date: date, end_date: date) -> np.ndarray:
    db = get_sql_db()
    embeddings = np.array( db.query(NewsEntry.summary_embedding).filter(
                NewsEntry.crawl_time >= start_date,
                NewsEntry.crawl_time < end_date,
            ).all())
    embeddings = embeddings.reshape(embeddings.shape[0], embeddings.shape[2]) 
    return embeddings
    
def show_distribution(embeddings: np.ndarray, plt_container: plt.Figure):
    subplot = plt_container.add_subplot(1, 3, 1)
    for dim in range(10):  # limit to first 5 dims for visualization
        sns.kdeplot(embeddings[:, dim], label=f'Dim {dim}', ax=subplot)
    subplot.legend()
    subplot.set_title('Distribution of Embedding Dimensions')

def show_pairwise_distances(embeddings: np.ndarray, plt_container: plt.Figure):
    # Calculate pairwise distances
    distances = pairwise_distances(embeddings)
    subplot = plt_container.add_subplot(1, 3, 2)
    dists_flat = distances[np.triu_indices_from(distances, k=1)]
    subplot.hist(dists_flat, bins=50)
    subplot.set_title('Pairwise Distance Distribution')
    print(f"Mean: {np.mean(dists_flat):.4f}, Median: {np.median(dists_flat):.4f}, Min: {np.min(dists_flat):.4f}, Max: {np.max(dists_flat):.4f}")

def show_tsne(embeddings: np.ndarray, plt_container: plt.Figure):
    tsne = TSNE(n_components=2, random_state=42, perplexity=30, n_iter=300)
    embeddings_2d = tsne.fit_transform(embeddings)

    subplot = plt_container.add_subplot(1, 3, 3)
    subplot.scatter(embeddings_2d[:, 0], embeddings_2d[:, 1], alpha=0.5)
    subplot.set_title('t-SNE Visualization of Embeddings')
    subplot.set_xlabel('t-SNE Component 1')
    subplot.set_ylabel('t-SNE Component 2')

embeddings = __get_embedding_data(date(2025, 5, 19), date(2025, 5, 25))
print(embeddings.shape)
plt_container = plt.figure(figsize=(20, 16))
show_distribution(embeddings, plt_container)
show_pairwise_distances(embeddings, plt_container)
show_tsne(embeddings, plt_container)
plt.suptitle(f"Embedding Analysis - {embeddings.shape[0]} samples, {embeddings.shape[1]} dimensions", 
                 fontsize=16)
    
# Adjust layout and spacing
plt.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.show()