// Obscure Bit - Editorial Home Page

document.addEventListener('DOMContentLoaded', function() {
  // Only run on home page
  if (document.querySelector('.ob-hero')) {
    initScrollReveal();
    initHeroParallax();
    initLinkHovers();
  }
});

// Scroll reveal animations
function initScrollReveal() {
  const reveals = document.querySelectorAll('.ob-today__story, .ob-link, .ob-manifesto__content');
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
      }
    });
  }, {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  });

  reveals.forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(30px)';
    el.style.transition = 'opacity 0.8s cubic-bezier(0.16, 1, 0.3, 1), transform 0.8s cubic-bezier(0.16, 1, 0.3, 1)';
    observer.observe(el);
  });
}

// Hero parallax on scroll
function initHeroParallax() {
  const hero = document.querySelector('.ob-hero');
  const heroContent = document.querySelector('.ob-hero__content');
  const scrollHint = document.querySelector('.ob-hero__scroll-hint');
  
  if (!hero || !heroContent) return;

  let ticking = false;

  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        const scrolled = window.pageYOffset;
        const heroHeight = hero.offsetHeight;
        
        if (scrolled < heroHeight) {
          const progress = scrolled / heroHeight;
          
          // Content fades and moves up
          heroContent.style.opacity = 1 - progress * 1.5;
          heroContent.style.transform = `translateY(${scrolled * 0.3}px)`;
          
          // Scroll hint fades out faster
          if (scrollHint) {
            scrollHint.style.opacity = 1 - progress * 3;
          }
        }
        
        ticking = false;
      });
      ticking = true;
    }
  });
}

// Enhanced link hover effects
function initLinkHovers() {
  const links = document.querySelectorAll('.ob-link');
  
  links.forEach(link => {
    link.addEventListener('mouseenter', function() {
      // Add subtle scale to siblings
      links.forEach(l => {
        if (l !== this && !l.classList.contains('ob-link--more')) {
          l.style.opacity = '0.6';
        }
      });
    });
    
    link.addEventListener('mouseleave', function() {
      links.forEach(l => {
        l.style.opacity = '1';
      });
    });
  });
}
