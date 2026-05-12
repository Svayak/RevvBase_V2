// Auto-uppercase reg.nr fields
document.querySelectorAll('input[name="regnr"]').forEach(function(el) {
  el.addEventListener('input', function() {
    var pos = this.selectionStart;
    this.value = this.value.toUpperCase();
    this.setSelectionRange(pos, pos);
  });
});

// Search auto-submit on clear
var searchInput = document.querySelector('.search-input');
if (searchInput) {
  searchInput.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      this.value = '';
      this.form.submit();
    }
  });
}
