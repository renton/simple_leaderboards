(function () {
  var container = document.getElementById('seed-calendar');
  if (!container) return;

  var activeDates = new Set(JSON.parse(container.dataset.active || '[]'));
  var hiddenInput = document.getElementById('seed-date-value');
  var selectedDate = hiddenInput.value || '';
  var form = hiddenInput.closest('form');

  var now = new Date();
  var todayStr = now.getFullYear() + '-'
    + String(now.getMonth() + 1).padStart(2, '0') + '-'
    + String(now.getDate()).padStart(2, '0');

  var viewYear, viewMonth;
  if (selectedDate) {
    viewYear = parseInt(selectedDate.slice(0, 4));
    viewMonth = parseInt(selectedDate.slice(5, 7)) - 1;
  } else {
    var sorted = Array.from(activeDates).sort();
    var latest = sorted[sorted.length - 1];
    if (latest) {
      viewYear = parseInt(latest.slice(0, 4));
      viewMonth = parseInt(latest.slice(5, 7)) - 1;
    } else {
      viewYear = now.getFullYear();
      viewMonth = now.getMonth();
    }
  }

  var MONTHS = ['January','February','March','April','May','June',
                'July','August','September','October','November','December'];
  var DOWS   = ['Su','Mo','Tu','We','Th','Fr','Sa'];

  function pad(n) { return String(n).padStart(2, '0'); }
  function ds(y, m, d) { return y + '-' + pad(m + 1) + '-' + pad(d); }
  function atToday() { return viewYear === now.getFullYear() && viewMonth === now.getMonth(); }

  function render() {
    var firstDow   = new Date(viewYear, viewMonth, 1).getDay();
    var daysInMon  = new Date(viewYear, viewMonth + 1, 0).getDate();

    var html = '<div class="cal-header">'
      + '<button type="button" class="cal-nav" id="cal-prev">&#8249;</button>'
      + '<span class="cal-month-label">' + MONTHS[viewMonth] + ' ' + viewYear + '</span>'
      + '<button type="button" class="cal-nav' + (atToday() ? ' cal-nav-disabled' : '') + '" id="cal-next">&#8250;</button>'
      + '</div>'
      + '<div class="cal-grid">';

    DOWS.forEach(function (d) { html += '<div class="cal-cell cal-dow">' + d + '</div>'; });

    for (var i = 0; i < firstDow; i++) html += '<div class="cal-cell"></div>';

    for (var day = 1; day <= daysInMon; day++) {
      var date = ds(viewYear, viewMonth, day);
      var cls = 'cal-cell cal-day';
      if (activeDates.has(date)) cls += ' has-scores';
      if (date === selectedDate)  cls += ' selected';
      if (date === todayStr)      cls += ' today';
      html += '<div class="' + cls + '" data-date="' + date + '">' + day + '</div>';
    }

    html += '</div>';

    if (selectedDate) {
      html += '<button type="button" class="cal-clear" id="cal-clear">&#215; normal play</button>';
    }

    container.innerHTML = html;

    container.querySelector('#cal-prev').addEventListener('click', function () {
      viewMonth--;
      if (viewMonth < 0) { viewMonth = 11; viewYear--; }
      render();
    });

    container.querySelector('#cal-next').addEventListener('click', function () {
      if (atToday()) return;
      viewMonth++;
      if (viewMonth > 11) { viewMonth = 0; viewYear++; }
      render();
    });

    container.querySelectorAll('.cal-day.has-scores').forEach(function (el) {
      el.addEventListener('click', function () {
        selectedDate = this.dataset.date;
        hiddenInput.value = selectedDate;
        form.submit();
      });
    });

    var clearBtn = container.querySelector('#cal-clear');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        selectedDate = '';
        hiddenInput.value = '';
        form.submit();
      });
    }
  }

  render();
})();
