<!DOCTYPE html>
<html>
<head>
<title>Loading Animation Example</title>
<style>
#loadingOverlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.7); /* Semi-transparent black background */
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000; /* Ensure it's on top */
}

#loadingScreen {
    display: flex;
    justify-content: center;
    align-items: center;
    animation: rotate 2s linear infinite;
}

#siteLogo {
    width: 100px;
    height: 100px;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
</head>
<body>
  <div id="loadingOverlay">
      <div id="loadingScreen">
          <img id="siteLogo" src="your_logo.png" alt="Loading..."> </div>
  </div>

  <div id="content">  <!-- Content of your page will go here -->
      <form id="searchForm">
          <input type="text" id="searchInput" placeholder="Search...">
          <button type="submit">Search</button>
      </form>
      <div class="featured-article card">
          <h5 class="card-title">Featured Article Title</h5>
          <div class="article-content">Featured Article Content</div>
      </div>
      <div class="article-list">
          <div class="card">
              <h5 class="h5">Article 1</h5>
          </div>
          <div class="card">
              <h5 class="h5">Article 2</h5>
          </div>
      </div>
  </div>

<script>
window.addEventListener('load', function() {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'none';
    }
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
</script>
</body>
</html>