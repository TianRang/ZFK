document.body.addEventListener('htmx:responseError', function(event) {
    console.error('HTMX error:', event.detail);
});
