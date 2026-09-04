/**
 * TipTapEditor — Rich text editor using TipTap
 * Features: Bold, Italic, Underline, BulletList, OrderedList, Heading H3,
 *           Undo/Redo, Clear Formatting, Image Embed (URL + upload)
 */
import { useState } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import Image from '@tiptap/extension-image';
import {
  Bold, Italic, Underline as UnderlineIcon, List, ListOrdered,
  Heading3, Undo2, Redo2, RemoveFormatting, ImageIcon, Link2
} from 'lucide-react';
import './TipTapEditor.css';

const TOOLBAR = [
  { icon: Bold,           action: e => e.chain().focus().toggleBold().run(),            active: e => e.isActive('bold'),            title: 'Bold (Ctrl+B)' },
  { icon: Italic,         action: e => e.chain().focus().toggleItalic().run(),          active: e => e.isActive('italic'),          title: 'Italic (Ctrl+I)' },
  { icon: UnderlineIcon,  action: e => e.chain().focus().toggleUnderline().run(),       active: e => e.isActive('underline'),       title: 'Underline (Ctrl+U)' },
  null,
  { icon: Heading3,       action: e => e.chain().focus().toggleHeading({ level: 3 }).run(), active: e => e.isActive('heading', { level: 3 }), title: 'Heading' },
  { icon: List,           action: e => e.chain().focus().toggleBulletList().run(),      active: e => e.isActive('bulletList'),      title: 'Bullet List' },
  { icon: ListOrdered,    action: e => e.chain().focus().toggleOrderedList().run(),     active: e => e.isActive('orderedList'),     title: 'Numbered List' },
  null,
  { icon: Undo2,          action: e => e.chain().focus().undo().run(),                  active: () => false,                        title: 'Undo (Ctrl+Z)' },
  { icon: Redo2,          action: e => e.chain().focus().redo().run(),                  active: () => false,                        title: 'Redo (Ctrl+Y)' },
  { icon: RemoveFormatting, action: e => e.chain().focus().clearNodes().unsetAllMarks().run(), active: () => false, title: 'Clear Formatting' },
];

export default function TipTapEditor({ value = '', onChange, minHeight = 180, readOnly = false }) {
  const [showImgDialog, setShowImgDialog] = useState(false);
  const [imgUrl, setImgUrl] = useState('');
  const [uploading, setUploading] = useState(false);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      Image.configure({ inline: false, allowBase64: true }),
    ],
    content: value,
    editable: !readOnly,
    onUpdate: ({ editor }) => {
      if (onChange) onChange(editor.getHTML());
    },
  });

  // Sync external content changes (avoids cursor jump)
  if (editor && value !== editor.getHTML() && !editor.isFocused) {
    editor.commands.setContent(value || '', false);
  }

  const insertImageByUrl = () => {
    const url = imgUrl.trim();
    if (!url) return;
    editor.chain().focus().setImage({ src: url, alt: 'image' }).run();
    setImgUrl('');
    setShowImgDialog(false);
  };

  const handleImageUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) { alert('Hanya file gambar yang diizinkan.'); return; }
    if (file.size > 5 * 1024 * 1024) { alert('Ukuran file maksimal 5 MB.'); return; }
    setUploading(true);
    const reader = new FileReader();
    reader.onload = (ev) => {
      editor.chain().focus().setImage({ src: ev.target.result, alt: file.name }).run();
      setUploading(false);
      setShowImgDialog(false);
    };
    reader.onerror = () => { setUploading(false); alert('Gagal membaca file.'); };
    reader.readAsDataURL(file);
  };

  return (
    <div className="tiptap-wrapper border rounded-lg overflow-hidden">
      {!readOnly && (
        <div className="tiptap-toolbar flex items-center gap-0.5 px-2 py-1.5 bg-muted/50 border-b flex-wrap">
          {TOOLBAR.map((btn, i) =>
            btn === null ? (
              <div key={i} className="w-px h-5 bg-border mx-1" />
            ) : (
              <button
                key={i}
                type="button"
                title={btn.title}
                data-testid={`tiptap-${btn.title?.toLowerCase().split(' ')[0]}`}
                onMouseDown={e => { e.preventDefault(); btn.action(editor); }}
                className={`w-7 h-7 rounded flex items-center justify-center transition-colors text-sm
                  ${editor && btn.active(editor)
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-background hover:border-border border border-transparent text-foreground/80'}`}
              >
                <btn.icon className="w-3.5 h-3.5" />
              </button>
            )
          )}

          {/* Divider + Image insert button */}
          <div className="w-px h-5 bg-border mx-1" />
          <div className="relative">
            <button
              type="button"
              title="Sisipkan Gambar"
              data-testid="tiptap-image"
              onMouseDown={e => { e.preventDefault(); setShowImgDialog(v => !v); setImgUrl(''); }}
              className={`w-7 h-7 rounded flex items-center justify-center transition-colors text-sm
                ${showImgDialog
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-background hover:border-border border border-transparent text-foreground/80'}`}
            >
              <ImageIcon className="w-3.5 h-3.5" />
            </button>

            {showImgDialog && (
              <div className="absolute top-9 left-0 z-50 bg-background border rounded-xl shadow-xl p-4 w-72 space-y-3">
                <p className="text-xs font-medium text-foreground">Sisipkan Gambar</p>

                <div className="flex gap-2">
                  <input
                    type="url"
                    placeholder="https://... (URL gambar)"
                    value={imgUrl}
                    onChange={e => setImgUrl(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); insertImageByUrl(); } }}
                    className="flex-1 border rounded-lg px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary"
                    data-testid="tiptap-image-url-input"
                  />
                  <button
                    type="button"
                    onClick={insertImageByUrl}
                    disabled={!imgUrl.trim()}
                    className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium disabled:opacity-50 hover:opacity-90"
                    data-testid="tiptap-image-url-insert"
                  >
                    <Link2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <div className="flex-1 h-px bg-border" />
                  <span>atau</span>
                  <div className="flex-1 h-px bg-border" />
                </div>

                <label className={`flex items-center justify-center gap-2 border-2 border-dashed rounded-lg px-3 py-3 text-xs cursor-pointer transition-colors
                  ${uploading ? 'opacity-50 cursor-not-allowed' : 'hover:border-primary hover:bg-primary/5 text-muted-foreground hover:text-primary'}`}>
                  <ImageIcon className="w-4 h-4" />
                  {uploading ? 'Membaca gambar...' : 'Unggah dari komputer'}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    disabled={uploading}
                    onChange={handleImageUpload}
                    data-testid="tiptap-image-file-input"
                  />
                </label>

                <button
                  type="button"
                  onClick={() => setShowImgDialog(false)}
                  className="text-xs text-muted-foreground hover:text-foreground w-full text-center"
                >
                  Batal
                </button>
              </div>
            )}
          </div>
        </div>
      )}
      <EditorContent
        editor={editor}
        data-testid="tiptap-editor-content"
        style={{ minHeight }}
        className="tiptap-content"
      />
    </div>
  );
}
