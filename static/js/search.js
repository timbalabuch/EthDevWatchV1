document.addEventListener('DOMContentLoaded', function() {
    // Hide loading screen once page is loaded
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.style.display = 'none';
    }

    const searchForm = document.getElementById('searchForm');
    const searchInput = document.getElementById('searchInput');
    const featuredArticle = document.querySelector('.featured-article');
    const articleList = document.querySelector('.article-list');

    if (searchForm && searchInput) {
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            performSearch();
        });

        // Also perform search while typing after a small delay
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(performSearch, 300);
        });

        function performSearch() {
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
                let hasVisibleArticles = false;

                articles.forEach(article => {
                    const title = article.querySelector('.card-title').textContent.toLowerCase();
                    const content = article.querySelector('.article-content')?.textContent.toLowerCase() || '';
                    const isMatch = title.includes(searchTerm) || content.includes(searchTerm);

                    article.style.display = isMatch ? 'block' : 'none';
                    if (isMatch) hasVisibleArticles = true;
                });

                // Show/hide no results message
                let noResultsMsg = articleList.querySelector('.no-results-message');
                if (!hasVisibleArticles) {
                    if (!noResultsMsg) {
                        noResultsMsg = document.createElement('div');
                        noResultsMsg.className = 'no-results-message alert alert-info mt-3';
                        noResultsMsg.textContent = 'No articles found matching your search.';
                        articleList.appendChild(noResultsMsg);
                    }
                    noResultsMsg.style.display = 'block';
                } else if (noResultsMsg) {
                    noResultsMsg.style.display = 'none';
                }
            }
        }

        // Reset display when search is cleared
        searchInput.addEventListener('input', function() {
            if (this.value.trim() === '') {
                if (featuredArticle) featuredArticle.style.display = 'block';
                if (articleList) {
                    const articles = articleList.querySelectorAll('.card');
                    articles.forEach(article => article.style.display = 'block');
                    const noResultsMsg = articleList.querySelector('.no-results-message');
                    if (noResultsMsg) noResultsMsg.style.display = 'none';
                }
            }
        });
    }
});