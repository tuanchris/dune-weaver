
export const translations = {
  en: {
    nav: {
      browse: 'Browse',
      playlists: 'Playlists',
      control: 'Control',
      led: 'LED',
      settings: 'Settings',
      draw: 'Draw',
    },
    browse: {
      title: 'Browse Patterns',
      search: 'Search patterns...',
      upload: 'Upload Pattern',
      no_patterns: 'No patterns found',
      patterns_available: 'patterns available',
    },
    control: {
      title: 'Table Control',
      subtitle: 'Manual controls for your sand table',
      home: 'Home',
      pause: 'Pause',
      resume: 'Resume',
      stop: 'Stop',
      speed: 'Speed',
      progress: 'Progress',
    },
    settings: {
      title: 'Settings',
      language: 'Language',
      theme: 'Theme',
      dark: 'Dark',
      light: 'Light',
      system: 'System',
    },
    draw: {
      title: 'Draw Pattern',
      save: 'Save Pattern',
      clear: 'Clear Canvas',
      undo: 'Undo',
      redo: 'Redo',
      export: 'Export THR',
      name_placeholder: 'Pattern Name',
      save_success: 'Pattern saved successfully',
    }
  },
  tr: {
    nav: {
      browse: 'Gözat',
      playlists: 'Oynatma Listeleri',
      control: 'Kontrol',
      led: 'LED',
      settings: 'Ayarlar',
      draw: 'Çizim',
    },
    browse: {
      title: 'Desenlere Gözat',
      search: 'Desen ara...',
      upload: 'Desen Yükle',
      no_patterns: 'Desen bulunamadı',
      patterns_available: 'desen mevcut',
    },
    control: {
      title: 'Masa Kontrolü',
      subtitle: 'Kum masanız için manuel kontroller',
      home: 'Eve Dön',
      pause: 'Duraklat',
      resume: 'Devam Et',
      stop: 'Durdur',
      speed: 'Hız',
      progress: 'İlerleme',
    },
    settings: {
      title: 'Ayarlar',
      language: 'Dil',
      theme: 'Tema',
      dark: 'Koyu',
      light: 'Açık',
      system: 'Sistem',
    },
    draw: {
      title: 'Desen Çiz',
      save: 'Deseni Kaydet',
      clear: 'Tuvali Temizle',
      undo: 'Geri Al',
      redo: 'İleri Al',
      export: 'THR Olarak Dışa Aktar',
      name_placeholder: 'Desen Adı',
      save_success: 'Desen başarıyla kaydedildi',
    }
  }
};

export type Language = 'en' | 'tr';
export type TranslationKeys = typeof translations.en;
