document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const searchInput = document.getElementById('searchInput');
    const articlesContainer = document.getElementById('articles');

    if (searchForm && searchInput) {
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const searchTerm = searchInput.value.trim().toLowerCase();
            
            const articles = articlesContainer.getElementsByTagName('article');
            Array.from(articles).forEach(article => {
                const title = article.querySelector('.card-title').textContent.toLowerCase();
                const content = article.querySelector('.card-text').textContent.toLowerCase();
                
                if (title.includes(searchTerm) || content.includes(searchTerm)) {
                    article.style.display = 'block';
                } else {
                    article.style.display = 'none';
                }
            });
        });

        searchInput.addEventListener('input', function() {
            if (this.value.trim() === '') {
                Array.from(articlesContainer.getElementsByTagName('article')).forEach(article => {
                    article.style.display = 'block';
                });
            }
        });
    }
});
