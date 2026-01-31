// Sticky post header and post page detection
function initStickyHeader() {
  // Remove any existing sticky elements
  const existingHeader = document.querySelector('.sticky-post-header');
  const existingButton = document.querySelector('.scroll-to-top');
  if (existingHeader) existingHeader.remove();
  if (existingButton) existingButton.remove();
  
  // Reset body attribute
  document.body.removeAttribute('data-page-type');
  
  const content = document.querySelector('.md-content__inner');
  
  // Check if this is a post page (has h1 in content, but not the home page)
  if (content) {
    const h1 = content.querySelector('h1');
    const isHomePage = window.location.pathname.endsWith('/b1ts/') || 
                       window.location.pathname.endsWith('/b1ts/index.html') ||
                       document.querySelector('.ob-hero');
    
    if (h1 && !isHomePage) {
      // Mark body as post page for CSS targeting
      document.body.setAttribute('data-page-type', 'post');
      
      // Get the post title (remove the permalink symbol)
      const postTitle = h1.textContent.replace('¶', '').trim();
      
      // Create sticky header element
      const stickyHeader = document.createElement('div');
      stickyHeader.className = 'sticky-post-header';
      
      const titleElement = document.createElement('h2');
      titleElement.className = 'sticky-post-header__title';
      titleElement.textContent = postTitle;
      
      stickyHeader.appendChild(titleElement);
      
      // Insert sticky header into body (not content)
      document.body.appendChild(stickyHeader);
      
      // Create scroll to top button
      const scrollToTopBtn = document.createElement('button');
      scrollToTopBtn.className = 'scroll-to-top';
      scrollToTopBtn.setAttribute('aria-label', 'Scroll to top');
      scrollToTopBtn.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15"></polyline></svg>';
      document.body.appendChild(scrollToTopBtn);
      
      // Scroll to top on click
      scrollToTopBtn.addEventListener('click', function() {
        window.scrollTo({
          top: 0,
          behavior: 'smooth'
        });
      });
      
      // Show/hide sticky title and scroll button based on scroll position
      let ticking = false;
      const titleOffset = h1.offsetTop + h1.offsetHeight;
      
      function updateStickyElements() {
        const scrollY = window.scrollY || window.pageYOffset;
        
        if (scrollY > titleOffset) {
          stickyHeader.classList.add('visible');
          scrollToTopBtn.classList.add('visible');
        } else {
          stickyHeader.classList.remove('visible');
          scrollToTopBtn.classList.remove('visible');
        }
        
        ticking = false;
      }
      
      window.addEventListener('scroll', function() {
        if (!ticking) {
          window.requestAnimationFrame(updateStickyElements);
          ticking = true;
        }
      });
      
      // Initial check
      updateStickyElements();
    }
  }
}

// Run on initial page load
document.addEventListener('DOMContentLoaded', initStickyHeader);

// Run on navigation (MkDocs Material instant loading)
if (typeof document$ !== 'undefined') {
  // MkDocs Material uses RxJS observables
  document$.subscribe(initStickyHeader);
} else {
  // Fallback for navigation events
  document.addEventListener('DOMContentSwitch', initStickyHeader);
}
