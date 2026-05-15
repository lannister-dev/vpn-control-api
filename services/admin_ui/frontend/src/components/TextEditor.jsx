import { useEffect } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Underline from "@tiptap/extension-underline";
import Placeholder from "@tiptap/extension-placeholder";
import { Icon } from "./Icon.jsx";
import "./TextEditor.css";

const TG_ALLOWED_TAGS = new Set([
  "b", "strong", "i", "em", "u", "s", "strike", "del",
  "code", "pre", "a", "br",
  "blockquote", "tg-spoiler",
]);

export function htmlForTelegram(html) {
  if (!html) return "";
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  const walk = (node) => {
    if (node.nodeType === 1) {
      const tag = node.tagName.toLowerCase();
      if (!TG_ALLOWED_TAGS.has(tag) && tag !== "p" && tag !== "ul" && tag !== "ol" && tag !== "li") {
        const text = document.createTextNode(node.textContent || "");
        node.replaceWith(text);
        return;
      }
      if (tag === "p") {
        const fragment = document.createDocumentFragment();
        for (const child of [...node.childNodes]) {
          walk(child);
          fragment.appendChild(child);
        }
        fragment.appendChild(document.createTextNode("\n\n"));
        node.replaceWith(fragment);
        return;
      }
      if (tag === "li") {
        const fragment = document.createDocumentFragment();
        fragment.appendChild(document.createTextNode("• "));
        for (const child of [...node.childNodes]) {
          walk(child);
          fragment.appendChild(child);
        }
        fragment.appendChild(document.createTextNode("\n"));
        node.replaceWith(fragment);
        return;
      }
      if (tag === "ul" || tag === "ol") {
        const fragment = document.createDocumentFragment();
        for (const child of [...node.childNodes]) {
          walk(child);
          fragment.appendChild(child);
        }
        node.replaceWith(fragment);
        return;
      }
      if (tag === "a") {
        const href = node.getAttribute("href") || "";
        const safeHref = /^(https?:|tg:|mailto:)/i.test(href) ? href : "";
        for (const attr of [...node.attributes]) node.removeAttribute(attr.name);
        if (safeHref) node.setAttribute("href", safeHref);
      } else {
        for (const attr of [...node.attributes]) node.removeAttribute(attr.name);
      }
      for (const child of [...node.childNodes]) walk(child);
    }
  };
  for (const child of [...tmp.childNodes]) walk(child);
  return tmp.innerHTML.replace(/\n{3,}/g, "\n\n").trim();
}

function ToolbarButton({ active, disabled, onClick, title, icon, label }) {
  return (
    <button
      type="button"
      className={`txed-tb-btn ${active ? "active" : ""}`}
      disabled={disabled}
      onClick={onClick}
      title={title}
      tabIndex={-1}
    >
      {icon && <Icon name={icon} size={13} />}
      {label && <span>{label}</span>}
    </button>
  );
}

export function TextEditor({ value, onChange, placeholder, minHeight = 80, autoFocus = false }) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        horizontalRule: false,
        bulletList: { keepMarks: true, keepAttributes: false },
        orderedList: false,
        codeBlock: { HTMLAttributes: { class: "txed-pre" } },
      }),
      Underline,
      Link.configure({ openOnClick: false, autolink: true, HTMLAttributes: { rel: "noopener" } }),
      Placeholder.configure({ placeholder: placeholder || "" }),
    ],
    content: value || "",
    autofocus: autoFocus,
    onUpdate: ({ editor }) => {
      const html = editor.getHTML();
      onChange?.(html === "<p></p>" ? "" : html);
    },
    editorProps: {
      attributes: { class: "txed-content", placeholder: placeholder || "" },
    },
  });

  useEffect(() => {
    if (!editor) return;
    const current = editor.getHTML();
    const incoming = value || "";
    if (incoming && incoming !== current) {
      editor.commands.setContent(incoming, { emitUpdate: false });
    } else if (!incoming && current && current !== "<p></p>") {
      editor.commands.clearContent();
    }
  }, [value, editor]);

  if (!editor) return null;

  const setLink = () => {
    const prev = editor.getAttributes("link").href || "";
    const url = window.prompt("Ссылка (https://…)", prev);
    if (url === null) return;
    if (!url) { editor.chain().focus().unsetLink().run(); return; }
    editor.chain().focus().setLink({ href: url }).run();
  };

  return (
    <div className="txed" style={{ "--txed-min-h": `${minHeight}px` }}>
      <div className="txed-toolbar">
        <ToolbarButton title="Жирный (⌘B)" icon="bold"
          active={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()} />
        <ToolbarButton title="Курсив (⌘I)" icon="italic"
          active={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()} />
        <ToolbarButton title="Подчёркнутый (⌘U)" icon="underline"
          active={editor.isActive("underline")}
          onClick={() => editor.chain().focus().toggleUnderline().run()} />
        <ToolbarButton title="Зачёркнутый" icon="strikethrough"
          active={editor.isActive("strike")}
          onClick={() => editor.chain().focus().toggleStrike().run()} />
        <span className="txed-tb-sep" />
        <ToolbarButton title="Код" icon="code"
          active={editor.isActive("code")}
          onClick={() => editor.chain().focus().toggleCode().run()} />
        <ToolbarButton title="Блок кода" label="{ }"
          active={editor.isActive("codeBlock")}
          onClick={() => editor.chain().focus().toggleCodeBlock().run()} />
        <span className="txed-tb-sep" />
        <ToolbarButton title="Цитата" icon="quote"
          active={editor.isActive("blockquote")}
          onClick={() => editor.chain().focus().toggleBlockquote().run()} />
        <ToolbarButton title="Список" icon="list"
          active={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()} />
        <span className="txed-tb-sep" />
        <ToolbarButton title="Спойлер" icon="eye-off"
          active={editor.isActive("tgSpoiler")}
          onClick={() => {
            const html = editor.getHTML();
            const sel = editor.state.selection;
            const text = editor.state.doc.textBetween(sel.from, sel.to);
            if (!text) return;
            editor.chain().focus().insertContent(`<tg-spoiler>${text}</tg-spoiler>`).run();
          }} />
        <ToolbarButton title="Ссылка" icon="link"
          active={editor.isActive("link")}
          onClick={setLink} />
      </div>
      <EditorContent editor={editor} />
    </div>
  );
}
