// Obscure Bit - Custom JavaScript

// Share functionality
function shareContent(url, title) {
  if (navigator.share) {
    navigator.share({
      title: title,
      url: url
    }).catch(() => {
      copyToClipboard(url);
    });
  } else {
    copyToClipboard(url);
  }
}

function copyToClipboard(text) {
  // Try modern clipboard API first
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast('Link copied!');
    }).catch(() => {
      fallbackCopy(text);
    });
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed'; // Prevent scrolling to bottom
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  
  try {
    const successful = document.execCommand('copy');
    if (successful) {
      showToast('Link copied!');
    } else {
      showToast('Copy failed');
    }
  } catch (err) {
    showToast('Copy failed');
  }
  
  document.body.removeChild(textarea);
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
  // Add event listeners to ALL share buttons
  document.querySelectorAll('.share-btn').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      const url = this.dataset.url || window.location.href;
      const title = this.dataset.title || document.title;
      shareContent(url, title);
    });
  });

  // Initialize expand buttons
  document.querySelectorAll('.expand-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      toggleStory(this);
    });
  });
});
