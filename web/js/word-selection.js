// word-selection.js — click / mousemove word cell selection.
// Operates on the single #interlinear element that holds the entire verse range.
(function () {
    const interlinear = document.getElementById('interlinear');
    if (!interlinear) return;

    function notifySelectionChanged() {
        if (window._gemRebuild) window._gemRebuild();
        if (window._refreshFromCells) window._refreshFromCells();
        if (window._analysisRebuild) window._analysisRebuild();
    }

    function clearAll() {
        interlinear.querySelectorAll('.word-cell.selected')
            .forEach(c => c.classList.remove('selected'));
        notifySelectionChanged();
    }

    // Track S/D key state for paint-select / paint-deselect
    let keyState = {
        s: false,
        d: false
    };

    document.addEventListener('keydown', ev => {
        if (ev.key === 's') keyState.s = true;
        if (ev.key === 'd') keyState.d = true;
        if (ev.key === 'Escape') clearAll();
    });

    document.addEventListener('keyup', ev => {
        if (ev.key === 's') keyState.s = false;
        if (ev.key === 'd') keyState.d = false;
    });

    // Prevent right-click menu so right-button painting works
    interlinear.addEventListener('contextmenu', ev => ev.preventDefault());

    // Click: toggle individual cell (variant-btn handled separately).
    interlinear.addEventListener('click', function (ev) {
        if (ev.target.closest('.variant-btn')) return;
        const cell = ev.target.closest('.word-cell');
        if (!cell) return;
        cell.classList.toggle('selected');
        notifySelectionChanged();
    });

    // Mousemove: paint select/deselect depending on S/D or mouse buttons.
    interlinear.addEventListener('mousemove', function (ev) {
        if (ev.target.closest('.variant-btn')) return;
        const cell = ev.target.closest('.word-cell');
        if (!cell) return;

        // Determine mode
        const isSelect   = keyState.s || ev.buttons === 1; // left button
        const isDeselect = keyState.d || ev.buttons === 2; // right button

        if (!isSelect && !isDeselect) return;

        if (isSelect) {
            if (!cell.classList.contains('selected')) {
                cell.classList.add('selected');
                notifySelectionChanged();
            }
        } else if (isDeselect) {
            if (cell.classList.contains('selected')) {
                cell.classList.remove('selected');
                notifySelectionChanged();
            }
        }
    });

    // × clear button in gematria panel.
    const clearBtn = document.getElementById('gem-clear');
    if (clearBtn) clearBtn.addEventListener('click', clearAll);
})();
