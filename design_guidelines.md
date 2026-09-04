{
  "meta": {
    "app_type": "saas_app/dashboard",
    "audience": ["karyawan pabrik garment", "manager", "staff finance", "staff HR"],
    "language": "id-ID",
    "tech": ["React 18 (.js/.jsx)", "Tailwind CSS", "shadcn/ui (JSX)", "Lucide Icons", "FastAPI"],
    "constraints": {
      "no_new_libraries": true,
      "allowed_existing": ["framer-motion", "recharts"],
      "single_file_components": true,
      "dark_light_mode": true,
      "no_transparent_background": true,
      "must_add_data_testid": true
    }
  },
  "brand_personality": {
    "keywords": ["enterprise-professional", "cepat dipindai", "rapi & padat", "glass-card premium", "minim distraksi"],
    "north_star": "Slack/Discord feel tapi versi enterprise: struktur jelas, density tinggi, status & workflow terbaca dalam 3 detik.",
    "do": [
      "Gunakan glass-card sebagai surface utama (mengikuti token --glass-bg/--card-surface).",
      "Gunakan aksen gradient hanya sebagai dekorasi section header (<=20% viewport).",
      "Prioritaskan keterbacaan tabel & thread (solid surface, border halus)."
    ],
    "dont": [
      "Jangan pakai background transparan untuk card/area baca.",
      "Jangan pakai gradient gelap/saturated (lihat aturan gradient).",
      "Jangan bikin layout serba center; gunakan pola baca kiri-ke-kanan." 
    ]
  },
  "design_tokens": {
    "note": "Sistem token sudah ada di /app/frontend/src/index.css (Galaxy Glass dark, Lavender Clean light, Classic). Portal baru harus memakai token yang sama. Tambahkan token baru hanya jika benar-benar perlu.",
    "recommended_additions_to_index_css": {
      "chat_specific": {
        "--chat-bubble-in": "hsl(var(--muted) / 0.65)",
        "--chat-bubble-out": "hsl(var(--primary) / 0.14)",
        "--chat-thread-divider": "hsl(var(--border) / 0.7)",
        "--presence-online": "hsl(var(--success))",
        "--presence-offline": "hsl(var(--muted-foreground))",
        "--mention": "hsl(var(--warning) / 0.18)",
        "--reaction-bg": "hsl(var(--muted) / 0.7)"
      },
      "data_dense": {
        "--table-row-hover": "hsl(var(--muted) / 0.55)",
        "--table-row-selected": "hsl(var(--primary) / 0.10)",
        "--chip-bg": "hsl(var(--muted) / 0.7)"
      }
    },
    "shadows": {
      "glass_card": "shadow-[var(--shadow-card)]",
      "focus_ring": "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--background))]"
    },
    "radius": {
      "cards": "rounded-[var(--radius-md)]",
      "inputs": "rounded-[var(--radius-sm)]",
      "chips": "rounded-full"
    }
  },
  "typography": {
    "fonts": {
      "already_loaded": ["Space Grotesk (display)", "Inter (UI/body)", "JetBrains Mono (mono)"]
    },
    "scale": {
      "h1": "text-4xl sm:text-5xl lg:text-6xl font-display tracking-[-0.02em]",
      "h2": "text-base md:text-lg text-muted-foreground",
      "body": "text-sm md:text-base font-ui",
      "small": "text-xs text-muted-foreground",
      "mono": "font-mono text-xs"
    },
    "enterprise_density_rules": [
      "Sidebar list item: text-sm, line-clamp-1.",
      "Table header: text-xs uppercase tracking-wide.",
      "Message body: text-sm leading-6 (desktop), text-sm leading-5 (mobile)."
    ]
  },
  "layout_and_grid": {
    "global_shell": {
      "pattern": "3-pane optional",
      "desktop": "Left sidebar (channels/DM) 280–320px, main thread flex-1, optional right drawer 320px",
      "mobile": "Sidebar via Sheet/Drawer; main thread full width; composer sticky bottom",
      "container_classes": "min-h-[calc(100vh-64px)] flex gap-4 p-4"
    },
    "communication_hub": {
      "structure": {
        "left_sidebar": "Channels + DM + quick actions",
        "main": "Header (channel meta + search) + ScrollArea thread + composer",
        "optional_right": "Anggota channel / file / pinned (Drawer on mobile)"
      },
      "key_spacing": {
        "thread_padding": "px-3 md:px-4 py-3",
        "message_gap": "space-y-3",
        "composer_padding": "p-3 md:p-4"
      }
    },
    "asset_management": {
      "tabs": ["Dashboard", "Aset", "Kategori", "Depresiasi"],
      "pattern": "Top KPI strip + filter bar + table + detail drawer",
      "density": "Gunakan grid 12 kolom untuk desktop; KPI 4-up; table full width; drawer untuk detail/edit"
    },
    "procurement": {
      "tabs": ["Semua PR", "Inbox Approval", "Buat PR"],
      "pattern": "List + status chips + right detail panel + timeline visual"
    }
  },
  "components": {
    "component_path": {
      "shadcn_primary": [
        "/app/frontend/src/components/ui/button.jsx",
        "/app/frontend/src/components/ui/input.jsx",
        "/app/frontend/src/components/ui/textarea.jsx",
        "/app/frontend/src/components/ui/tabs.jsx",
        "/app/frontend/src/components/ui/table.jsx",
        "/app/frontend/src/components/ui/badge.jsx",
        "/app/frontend/src/components/ui/avatar.jsx",
        "/app/frontend/src/components/ui/scroll-area.jsx",
        "/app/frontend/src/components/ui/separator.jsx",
        "/app/frontend/src/components/ui/dialog.jsx",
        "/app/frontend/src/components/ui/drawer.jsx",
        "/app/frontend/src/components/ui/sheet.jsx",
        "/app/frontend/src/components/ui/popover.jsx",
        "/app/frontend/src/components/ui/tooltip.jsx",
        "/app/frontend/src/components/ui/dropdown-menu.jsx",
        "/app/frontend/src/components/ui/command.jsx",
        "/app/frontend/src/components/ui/calendar.jsx",
        "/app/frontend/src/components/ui/glass.jsx",
        "/app/frontend/src/components/ui/sonner.jsx",
        "/app/frontend/src/components/ui/skeleton.jsx",
        "/app/frontend/src/components/ui/progress.jsx",
        "/app/frontend/src/components/ui/collapsible.jsx",
        "/app/frontend/src/components/ui/resizable.jsx"
      ],
      "notes": {
        "no_html_dropdown": "Untuk dropdown/select/menu gunakan shadcn dropdown-menu/select/command.",
        "toasts": "Gunakan Sonner (/app/frontend/src/components/ui/sonner.jsx)."
      }
    },
    "communication_hub_components": {
      "sidebar": {
        "use": ["ScrollArea", "Collapsible", "Badge", "Button", "Input", "Tooltip"],
        "patterns": [
          "Section header (Channels/DM) + tombol tambah (icon) + collapse",
          "Item states: default/hover/active/unread/mention",
          "Unread badge: Badge variant secondary + count"
        ],
        "item_classes": {
          "base": "group flex items-center gap-2 px-2.5 py-2 rounded-[var(--radius-sm)] text-sm text-[hsl(var(--sidebar-foreground))] hover:bg-[var(--nav-pill-bg)]",
          "active": "bg-[var(--nav-pill-active)] text-foreground shadow-[var(--shadow-glow-blue)]",
          "unread_dot": "h-2 w-2 rounded-full bg-[hsl(var(--info))]",
          "presence_dot_online": "h-2.5 w-2.5 rounded-full bg-[hsl(var(--success))] ring-2 ring-[hsl(var(--background))]",
          "presence_dot_offline": "h-2.5 w-2.5 rounded-full bg-[hsl(var(--muted-foreground))] ring-2 ring-[hsl(var(--background))] opacity-60"
        }
      },
      "thread": {
        "use": ["ScrollArea", "Avatar", "Badge", "Tooltip", "DropdownMenu", "Separator"],
        "message_row": {
          "layout": "Avatar (optional) + header (nama, waktu) + bubble + meta",
          "hover_actions": "Muncul saat hover: reply, react, more (DropdownMenu)",
          "classes": {
            "row": "group flex gap-3 px-3 md:px-4 py-2 rounded-[var(--radius-sm)] hover:bg-[hsl(var(--muted)/0.35)]",
            "bubble": "max-w-[min(720px,100%)] rounded-[var(--radius-md)] border border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2",
            "bubble_reply": "border-l-2 border-l-[hsl(var(--primary))]",
            "meta": "mt-1 flex flex-wrap items-center gap-2"
          }
        },
        "reactions": {
          "pattern": "Chip kecil di bawah bubble; klik membuka Popover emoji picker sederhana (grid emoji statis untuk MVP)",
          "classes": {
            "chip": "inline-flex items-center gap-1 rounded-full border border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.55)] px-2 py-0.5 text-xs hover:bg-[hsl(var(--muted)/0.75)]"
          }
        },
        "typing_indicator": {
          "pattern": "Bar kecil di bawah thread: Avatar mini + teks 'Rina sedang mengetik…' + 3 dots anim",
          "classes": {
            "wrap": "px-3 md:px-4 py-2 text-xs text-muted-foreground flex items-center gap-2",
            "dots": "inline-flex gap-1",
            "dot": "h-1.5 w-1.5 rounded-full bg-[hsl(var(--muted-foreground))]"
          },
          "motion": "Animasi dots via keyframes opacity/translateY kecil; matikan saat prefers-reduced-motion"
        }
      },
      "composer": {
        "use": ["Textarea", "Button", "Popover", "Tooltip", "Dialog"],
        "pattern": [
          "Composer sticky bottom dalam card solid (bukan transparan)",
          "Toolbar: emoji, attach, mention, kirim",
          "Reply context bar di atas textarea saat reply"
        ],
        "classes": {
          "wrap": "sticky bottom-0 z-10 border-t border-[hsl(var(--border))] bg-[hsl(var(--background))]",
          "inner": "mx-0 p-3 md:p-4",
          "card": "rounded-[var(--radius-md)] border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-[var(--shadow-card)]",
          "textarea": "min-h-[44px] max-h-[160px] resize-none",
          "send_btn": "h-9 px-4 rounded-[var(--radius-sm)]"
        },
        "file_upload": {
          "pattern": "Input type=file hidden + Button 'Lampirkan' trigger; tampilkan chip file terpilih",
          "chip_classes": "inline-flex items-center gap-2 rounded-full border border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.55)] px-3 py-1 text-xs"
        }
      }
    },
    "asset_management_components": {
      "dashboard": {
        "use": ["Card", "Badge", "Progress"],
        "kpi_tile": {
          "pattern": "4 KPI cards: Total Aset, NBV, Depresiasi Bulan Ini, Aset Perlu Maintenance",
          "classes": "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3"
        },
        "charts": {
          "use": ["recharts"],
          "patterns": [
            "Line chart: tren depresiasi",
            "Bar chart: aset per kategori",
            "Donut: status aset (aktif/rusak/dijual)"
          ],
          "chart_container_classes": "rounded-[var(--radius-md)] border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4"
        }
      },
      "asset_table": {
        "use": ["Table", "Input", "Select", "DropdownMenu", "Badge", "PaginationBar"],
        "pattern": [
          "Filter bar sticky: Search + Kategori + Lokasi + Status + Rentang tanggal",
          "Table header sticky (CSS) + row hover",
          "Row click membuka Drawer detail"
        ],
        "classes": {
          "filter_bar": "sticky top-0 z-10 bg-[hsl(var(--background))] pb-3",
          "table_wrap": "rounded-[var(--radius-md)] border border-[hsl(var(--border))] bg-[hsl(var(--card))] overflow-hidden",
          "table": "text-sm",
          "row_hover": "hover:bg-[hsl(var(--muted)/0.35)]"
        }
      },
      "asset_form": {
        "use": ["Form", "Input", "Select", "Calendar", "Textarea", "Dialog"],
        "pattern": "Form 2 kolom desktop, 1 kolom mobile; sectioning: Identitas, Nilai & Depresiasi, Penempatan, Dokumen",
        "classes": {
          "grid": "grid grid-cols-1 md:grid-cols-2 gap-4",
          "section": "rounded-[var(--radius-md)] border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4"
        }
      },
      "asset_detail": {
        "use": ["Drawer", "Tabs", "Table", "Badge"],
        "tabs": ["Ringkasan", "Assignment", "Maintenance", "Riwayat Depresiasi"],
        "pattern": "Drawer kanan (desktop) / bottom drawer (mobile) dengan header ringkas + actions"
      }
    },
    "procurement_components": {
      "list_and_inbox": {
        "use": ["Tabs", "Table", "Badge", "DropdownMenu", "Sheet"],
        "pattern": "Semua PR: table; Inbox: list card + quick approve/reject; detail di panel kanan"
      },
      "timeline": {
        "use": ["Separator", "Badge"],
        "pattern": "Timeline vertikal: step node + garis; status warna (success/warning/destructive/info)",
        "classes": {
          "wrap": "space-y-3",
          "item": "flex gap-3",
          "node": "mt-1 h-2.5 w-2.5 rounded-full",
          "line": "ml-[5px] w-px bg-[hsl(var(--border))]"
        },
        "motion": "Saat membuka detail PR, timeline items masuk dengan stagger ringan (framer-motion)"
      }
    }
  },
  "motion_and_microinteractions": {
    "rules": [
      "Tidak boleh transition: all. Gunakan transition-colors, transition-opacity, transition-shadow.",
      "Hover: naikkan elevasi card (shadow-card -> shadow-soft) + border lebih jelas.",
      "Active press: scale-95 hanya untuk tombol (bukan container besar)."
    ],
    "chat": {
      "message_hover": "Action bar muncul dengan opacity transition (dur-150) + translateY kecil (2px)",
      "new_message": "AnimatePresence: fade-in + slide-up 6px (dur-200)",
      "typing_dots": "keyframes pulse 1.2s stagger"
    },
    "tables": {
      "row_hover": "transition-colors dur-150",
      "drawer_open": "framer-motion slide-in dari kanan (desktop) / bawah (mobile)"
    },
    "reduced_motion": "Hormati prefers-reduced-motion: matikan twinkle starfield anim & typing dots"
  },
  "accessibility": {
    "keyboard": [
      "Sidebar items harus focusable (Button/Link) dengan focus ring jelas.",
      "Composer: Enter untuk kirim, Shift+Enter newline (jelaskan hint).",
      "Table: row actions via DropdownMenu accessible."
    ],
    "contrast": [
      "Badge unread harus kontras (gunakan bg-muted + text-foreground).",
      "Presence dot harus punya ring agar terlihat di dark/light."
    ],
    "aria": [
      "Typing indicator gunakan aria-live=polite.",
      "Unread count gunakan aria-label 'Belum dibaca: X'."
    ]
  },
  "data_testid_conventions": {
    "format": "kebab-case, berbasis peran",
    "examples": [
      "data-testid=\"commhub-channel-item-<id>\"",
      "data-testid=\"commhub-dm-item-<id>\"",
      "data-testid=\"commhub-message-composer-textarea\"",
      "data-testid=\"commhub-message-send-button\"",
      "data-testid=\"asset-table-search-input\"",
      "data-testid=\"asset-create-submit-button\"",
      "data-testid=\"procurement-approval-approve-button\""
    ]
  },
  "page_blueprints": {
    "CommunicationHubPortal.jsx": {
      "header": "Nama channel + deskripsi singkat + tombol 'Detail' (opens Sheet) + search kecil",
      "sidebar_sections": ["Favorit", "Channels", "Pesan Langsung"],
      "empty_states": {
        "no_channel_selected": "Pilih channel untuk mulai membaca pesan.",
        "no_messages": "Belum ada pesan. Mulai percakapan pertama."
      }
    },
    "AssetManagementPortal.jsx": {
      "tabs": ["Dashboard", "Aset", "Kategori", "Depresiasi"],
      "dashboard_widgets": ["KPI strip", "Grafik depresiasi", "Aset mendekati akhir masa manfaat", "Maintenance due"],
      "aset_tab": "Filter bar + table + drawer detail",
      "depresiasi_tab": "Posting depresiasi (CTA) + riwayat posting + chart"
    },
    "ProcurementRequestModule.jsx": {
      "tabs": ["Semua PR", "Inbox Approval", "Buat PR"],
      "buat_pr": "Form bertahap: Info PR -> Item -> Lampiran -> Ringkasan",
      "inbox": "List PR yang butuh aksi + quick approve/reject + timeline"
    }
  },
  "image_urls": {
    "usage_rules": [
      "Gunakan gambar hanya untuk empty state/hero kecil di dashboard; jangan ganggu area baca chat/tabel.",
      "Pastikan gambar tidak jadi background transparan; taruh dalam Card solid."
    ],
    "categories": [
      {
        "category": "asset-dashboard-hero",
        "description": "Gambar kecil untuk header Dashboard Aset (opsional, 20% area).",
        "urls": [
          "https://images.pexels.com/photos/31019572/pexels-photo-31019572.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
          "https://images.pexels.com/photos/4492087/pexels-photo-4492087.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"
        ]
      },
      {
        "category": "communication-hub-empty-state",
        "description": "Ilustrasi foto ringan untuk empty state 'Pilih channel' atau 'Belum ada pesan'.",
        "urls": [
          "https://images.pexels.com/photos/12903168/pexels-photo-12903168.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
          "https://images.unsplash.com/photo-1576267461022-bc8727880adb?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
        ]
      }
    ]
  },
  "instructions_to_main_agent": {
    "implementation_notes": [
      "Ikuti token theme yang sudah ada di index.css; jangan hardcode warna hex kecuali untuk ilustrasi kecil.",
      "Gunakan GlassPanel dari /components/ui/glass.jsx untuk card utama; namun area baca (thread/tabel) tetap solid bg-card agar tidak transparan.",
      "Composer chat harus sticky bottom dan tidak menutupi ScrollArea; gunakan padding-bottom pada thread setara tinggi composer.",
      "Untuk emoji picker MVP tanpa library baru: Popover berisi grid emoji statis + search sederhana (Input) opsional.",
      "Reactions: gunakan Badge/Chip kecil; hover menampilkan Tooltip daftar reaktor.",
      "Typing indicator: aria-live=polite; tampilkan maksimal 2 nama lalu '+N lainnya'.",
      "Asset table: gunakan shadcn Table + PaginationBar; filter bar sticky; row click membuka Drawer detail.",
      "Procurement timeline: implementasi vertikal stepper (div + pseudo line) + framer-motion stagger saat open detail.",
      "Semua tombol/input/link/row-action wajib punya data-testid."
    ],
    "suggested_testids": {
      "commhub": [
        "commhub-sidebar-search-input",
        "commhub-create-channel-button",
        "commhub-create-dm-button",
        "commhub-thread-scrollarea",
        "commhub-message-composer-textarea",
        "commhub-message-emoji-button",
        "commhub-message-attach-button",
        "commhub-message-send-button",
        "commhub-message-reaction-button",
        "commhub-message-reply-button"
      ],
      "asset": [
        "asset-tabs-dashboard",
        "asset-tabs-aset",
        "asset-table-search-input",
        "asset-filter-status-select",
        "asset-create-open-dialog-button",
        "asset-create-submit-button",
        "asset-detail-drawer",
        "asset-maintenance-add-button"
      ],
      "procurement": [
        "procurement-tabs-semua",
        "procurement-tabs-inbox",
        "procurement-tabs-buat",
        "procurement-create-submit-button",
        "procurement-approval-approve-button",
        "procurement-approval-reject-button",
        "procurement-timeline"
      ]
    }
  },
  "general_ui_ux_design_guidelines_appendix": "<General UI UX Design Guidelines>\n    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.\n</General UI UX Design Guidelines>"
}
