// Obscure Bit - Custom JavaScript

// Share functionality
function shareContent(url, title) {
  if (navigator.share) {
    navigator.share({
      title: title,
      url: url
    }).catch(console.error);
  } else {
    copyToClipboard(url);
  }
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast('Link copied!');
  }).catch(() => {
    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    showToast('Link copied!');
  });
}

function showToast(message) {
  let toast = document.querySelector('.toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.className = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('show');
  
  setTimeout(() => {
    toast.classList.remove('show');
  }, 2000);
}

// Story expand/collapse
function toggleStory(button) {
  const preview = button.previousElementSibling;
  if (preview.classList.contains('expanded')) {
    preview.classList.remove('expanded');
    button.textContent = 'Read full story';
  } else {
    preview.classList.add('expanded');
    button.textContent = 'Collapse';
  }
}

// Initialize share buttons on page load
document.addEventListener('DOMContentLoaded', function() {
  // Add share buttons to content cards
  document.querySelectorAll('.content-card').forEach(card => {
    const shareBtn = card.querySelector('.share-btn');
    if (shareBtn) {
      shareBtn.addEventListener('click', function() {
        const url = this.dataset.url || window.location.href;
        const title = this.dataset.title || document.title;
        shareContent(url, title);
      });
    }
  });

  // Initialize expand buttons
  document.querySelectorAll('.expand-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      toggleStory(this);
    });
  });
});
