/*
 * Word/Excel Style Rich Text Editor
 * Wires every [data-rte] block rendered by templates/includes/rich_text_editor.html.
 * Each block keeps its own toolbar, editor and hidden textarea, so several editors
 * can live on one page (e.g. Admin Fast Post modal + other forms).
 *
 * To replace the content from other scripts:
 *   textarea.value = '...'; textarea.dispatchEvent(new Event('rte:reload'));
 */
(function () {
    'use strict';

    function looksLikeHtml(text) {
        return text.includes('<') && text.includes('>');
    }

    function initEditor(root) {
        if (root.dataset.rteReady) return;
        root.dataset.rteReady = '1';

        const editor = root.querySelector('.rte-editor');
        const input = root.querySelector('.rte-input');
        if (!editor || !input) return;

        function loadFromInput() {
            const raw = input.value || '';
            editor.innerHTML = looksLikeHtml(raw) ? raw : raw.replace(/\n/g, '<br>');
        }
        loadFromInput();
        input.addEventListener('rte:reload', loadFromInput);

        // Keep text selection range
        let savedRange = null;
        function saveSelection() {
            const sel = window.getSelection();
            if (sel.rangeCount > 0) {
                const range = sel.getRangeAt(0);
                if (editor.contains(range.commonAncestorContainer)) {
                    savedRange = range;
                }
            }
        }
        function restoreSelection() {
            if (savedRange) {
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(savedRange);
            }
        }

        // selectionchange also catches Cmd+A / Shift+Arrow on macOS, where keyup
        // never fires for keys pressed while Cmd is held.
        document.addEventListener('selectionchange', saveSelection);

        function syncContent() {
            input.value = editor.innerHTML;
        }

        editor.addEventListener('input', syncContent);
        editor.addEventListener('blur', syncContent);

        function afterCommand() {
            editor.focus();
            saveSelection();
            syncContent();
        }

        // Prevent toolbar buttons from stealing focus & collapsing selection
        root.querySelectorAll('.btn-rte-cmd, .btn-rte-color, .btn-rte-hilite, .btn-rte-insert-link, .btn-rte-remove-link').forEach(function (btn) {
            btn.addEventListener('mousedown', function (e) {
                e.preventDefault();
            });
        });

        // 1. Basic formatting commands (Bold, Italic, Underline, Lists, RemoveFormat)
        root.querySelectorAll('.btn-rte-cmd').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                restoreSelection();
                document.execCommand(this.getAttribute('data-cmd'), false, null);
                afterCommand();
            });
        });

        // 2. Font Colors
        root.querySelectorAll('.btn-rte-color').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                restoreSelection();
                document.execCommand('foreColor', false, this.getAttribute('data-color'));
                afterCommand();
            });
        });

        // Custom Color Picker
        const customColorInput = root.querySelector('.rte-custom-color');
        if (customColorInput) {
            customColorInput.addEventListener('input', function () {
                restoreSelection();
                document.execCommand('foreColor', false, this.value);
                afterCommand();
            });
        }

        // 3. Highlight Background Colors
        root.querySelectorAll('.btn-rte-hilite').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                restoreSelection();
                const color = this.getAttribute('data-color');
                if (!document.execCommand('hiliteColor', false, color)) {
                    document.execCommand('backColor', false, color);
                }
                afterCommand();
            });
        });

        // 4. Insert Link
        const insertLinkBtn = root.querySelector('.btn-rte-insert-link');
        if (insertLinkBtn) {
            insertLinkBtn.addEventListener('click', function (e) {
                e.preventDefault();
                restoreSelection();
                const sel = window.getSelection();
                if (!sel.rangeCount || sel.isCollapsed) {
                    alert('กรุณาคลุมดำ (ไฮไลท์) ข้อความที่ต้องการใส่ลิงก์ก่อนครับ');
                    return;
                }
                const url = prompt('กรุณากรอกลิงก์ที่ต้องการเชื่อมโยง (เช่น https://facebook.com/...):', 'https://');
                if (url && url.trim() && url.trim() !== 'https://') {
                    document.execCommand('createLink', false, url.trim());
                    editor.querySelectorAll('a').forEach(function (a) {
                        a.target = '_blank';
                        a.rel = 'noopener noreferrer';
                        a.className = 'text-blue-600 underline font-bold hover:text-blue-800 transition-colors';
                    });
                    afterCommand();
                }
            });
        }

        // Remove Link
        const removeLinkBtn = root.querySelector('.btn-rte-remove-link');
        if (removeLinkBtn) {
            removeLinkBtn.addEventListener('click', function (e) {
                e.preventDefault();
                restoreSelection();
                document.execCommand('unlink', false, null);
                afterCommand();
            });
        }

        // Form Submit Backup Sync
        const form = root.closest('form');
        if (form) {
            form.addEventListener('submit', syncContent);
        }
    }

    function initAll() {
        document.querySelectorAll('[data-rte]').forEach(initEditor);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
