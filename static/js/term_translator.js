document.addEventListener('DOMContentLoaded', () => {
    // Dictionary of technical terms and their explanations
    const technicalTerms = {};
    
    // Function to highlight technical terms in the content
    function highlightTechnicalTerms() {
        const content = document.querySelector('.ethereum-article');
        if (!content) return;
        
        // Get all text nodes in the content
        const walk = document.createTreeWalker(
            content,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let node;
        while (node = walk.nextNode()) {
            Object.keys(technicalTerms).forEach(term => {
                if (node.textContent.includes(term)) {
                    const regex = new RegExp(`\\b${term}\\b`, 'g');
                    const span = document.createElement('span');
                    span.innerHTML = node.textContent.replace(
                        regex,
                        `<span class="technical-term" data-term="${term}">${term}</span>`
                    );
                    node.parentNode.replaceChild(span, node);
                }
            });
        }
    }
    
    // Function to show tooltip with explanation
    function showTooltip(event) {
        const term = event.target.dataset.term;
        if (!term || !technicalTerms[term]) return;
        
        const tooltip = document.createElement('div');
        tooltip.className = 'term-tooltip';
        tooltip.textContent = technicalTerms[term];
        
        // Position tooltip near the term
        const rect = event.target.getBoundingClientRect();
        tooltip.style.left = `${rect.left}px`;
        tooltip.style.top = `${rect.bottom + 5}px`;
        
        document.body.appendChild(tooltip);
        
        // Remove tooltip when mouse leaves the term
        event.target.addEventListener('mouseleave', () => {
            tooltip.remove();
        });
    }
    
    // Fetch technical terms from the server
    fetch('/api/technical-terms')
        .then(response => response.json())
        .then(terms => {
            Object.assign(technicalTerms, terms);
            highlightTechnicalTerms();
            
            // Add event listeners for tooltips
            document.querySelectorAll('.technical-term').forEach(term => {
                term.addEventListener('mouseenter', showTooltip);
            });
        })
        .catch(console.error);
});
