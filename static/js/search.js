document.addEventListener('DOMContentLoaded', function() {
    // Hide loading screen once page is loaded
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) {
        loadingScreen.style.display = 'none';
    }

    const searchForm = document.getElementById('searchForm');
    const searchInput = document.getElementById('searchInput');
    const articleList = document.querySelector('.article-list');
    const featuredArticle = document.querySelector('.featured-article');
    let noResultsMessage = null;

    function showNoResults(container, show) {
        // Remove existing message if it exists
        if (noResultsMessage) {
            noResultsMessage.remove();
            noResultsMessage = null;
        }

        if (show) {
            noResultsMessage = document.createElement('div');
            noResultsMessage.className = 'alert alert-info mt-3';
            noResultsMessage.textContent = 'No matching articles found';
            container.appendChild(noResultsMessage);
        }
    }

    function searchInArticle(element, searchTerm) {
        if (!element) return false;

        const title = element.querySelector('.card-title, .h5')?.textContent.toLowerCase() || '';
        const summary = element.querySelector('.article-summary')?.textContent.toLowerCase() || '';
        const content = element.textContent.toLowerCase();

        return title.includes(searchTerm) || 
               summary.includes(searchTerm) || 
               content.includes(searchTerm);
    }

    if (searchForm && searchInput) {
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const searchTerm = searchInput.value.trim().toLowerCase();
            let hasResults = false;

            // Search in featured article
            if (featuredArticle) {
                const isMatch = searchInArticle(featuredArticle, searchTerm);
                featuredArticle.style.display = isMatch ? 'block' : 'none';
                hasResults = hasResults || isMatch;
            }

            // Search in article list
            if (articleList) {
                const articles = articleList.querySelectorAll('.card');
                let listHasResults = false;

                articles.forEach(article => {
                    const isMatch = searchInArticle(article, searchTerm);
                    article.style.display = isMatch ? 'block' : 'none';
                    listHasResults = listHasResults || isMatch;
                });

                hasResults = hasResults || listHasResults;
                showNoResults(articleList, !listHasResults && articles.length > 0);
            }

            // If no featured article and no article list has results
            if (!hasResults && !articleList && !featuredArticle) {
                showNoResults(searchForm.parentElement, true);
            }
        });

        // Reset display when search is cleared
        searchInput.addEventListener('input', function() {
            if (this.value.trim() === '') {
                if (featuredArticle) {
                    featuredArticle.style.display = 'block';
                }
                if (articleList) {
                    const articles = articleList.querySelectorAll('.card');
                    articles.forEach(article => article.style.display = 'block');
                }
                showNoResults(articleList || searchForm.parentElement, false);
            }
        });
    }
});