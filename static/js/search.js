document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const searchInput = document.getElementById('searchInput');
    const articleList = document.querySelector('.article-list');
    const featuredArticle = document.querySelector('.featured-article');

    if (searchForm && searchInput) {
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const searchTerm = searchInput.value.trim().toLowerCase();

            // Search in featured article
            if (featuredArticle) {
                const featuredTitle = featuredArticle.querySelector('.card-title').textContent.toLowerCase();
                const featuredContent = featuredArticle.querySelector('.article-content').textContent.toLowerCase();

                featuredArticle.style.display = 
                    (featuredTitle.includes(searchTerm) || featuredContent.includes(searchTerm)) 
                    ? 'block' 
                    : 'none';
            }

            // Search in article list
            if (articleList) {
                const articles = articleList.querySelectorAll('.card');
                articles.forEach(article => {
                    const title = article.querySelector('.h5').textContent.toLowerCase();
                    article.style.display = title.includes(searchTerm) ? 'block' : 'none';
                });
            }
        });

        // Reset display when search is cleared
        searchInput.addEventListener('input', function() {
            if (this.value.trim() === '') {
                if (featuredArticle) featuredArticle.style.display = 'block';
                if (articleList) {
                    const articles = articleList.querySelectorAll('.card');
                    articles.forEach(article => article.style.display = 'block');
                }
            }
        });
    }
});