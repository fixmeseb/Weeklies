// script.js – light enhancements for the simple Flask site
document.addEventListener('DOMContentLoaded', () => {
  // Mark active nav link
  const here = window.location.pathname.replace(/\/+$/,'') || '/';
  document.querySelectorAll('nav a[href]').forEach(a => {
    const path = a.getAttribute('href').replace(/\/+$/,'') || '/';
    if (path === here) a.setAttribute('aria-current', 'page');
  });

  // Confirm actions
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', (e) => {
      const msg = el.getAttribute('data-confirm') || 'Are you sure?';
      if (!confirm(msg)) e.preventDefault();
    });
  });

  // Simple auto-hide for flash messages
  document.querySelectorAll('.flash[data-autohide]').forEach(el => {
    const ms = parseInt(el.getAttribute('data-autohide'), 10) || 3500;
    setTimeout(() => { el.style.display = 'none'; }, ms);
  });

  // Menu generation loading spinner with AJAX
  (function setupMenuLoading() {
    const form = document.querySelector('form[action*="menu/generate"]');
    const generateBtn = document.getElementById('generateMenuBtn');
    const loadingDiv = document.getElementById('menuLoading');
    const errorDiv = document.getElementById('menuError');

    if (!form || !generateBtn || !loadingDiv) {
      console.warn('Menu loading elements not found');
      return;
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      console.log('Menu generation form submitted');
      
      // Collect form data
      const formData = new FormData(form);
      if (errorDiv) {
        errorDiv.hidden = true;
        errorDiv.textContent = '';
      }
      
      // Show spinner - make absolutely visible
      loadingDiv.style.display = 'block';
      loadingDiv.style.visibility = 'visible';
      loadingDiv.style.opacity = '1';
      generateBtn.disabled = true;
      console.log('Loading spinner shown');
      
      // Scroll to spinner
      loadingDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      
      try {
        // Send AJAX request
        console.log('Sending menu generation request to:', form.action);
        const response = await fetch(form.action, {
          method: 'POST',
          headers: { 'Accept': 'application/json' },
          body: formData
        });
        const result = await response.json();
        
        console.log('Response received:', response.status);
        
        if (response.ok && result.ok) {
          console.log('Generation successful, redirecting...');
          // Small delay to ensure spinner is visible before redirect
          setTimeout(() => {
            // Open on the days just planned
            const start = formData.get('start_date');
            window.location.href = start ? '/?week=' + encodeURIComponent(start) : '/';
          }, 100);
        } else {
          console.error('Generation failed with status:', response.status);
          // Show error and hide spinner
          if (errorDiv) {
            errorDiv.textContent = result.error || 'Menu generation failed. Please try again.';
            errorDiv.hidden = false;
          }
          loadingDiv.style.display = 'none';
          generateBtn.disabled = false;
        }
      } catch (error) {
        console.error('Error generating menu:', error);
        if (errorDiv) {
          errorDiv.textContent = 'Menu generation failed. Please try again.';
          errorDiv.hidden = false;
        }
        loadingDiv.style.display = 'none';
        generateBtn.disabled = false;
      }
    });
  })();
});

// Add spin animation
const style = document.createElement('style');
style.textContent = `
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
`;
document.head.appendChild(style);
