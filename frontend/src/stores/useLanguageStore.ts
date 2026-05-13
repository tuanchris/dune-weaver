import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { translations } from '@/lib/translations';
import type { Language } from '@/lib/translations';

interface LanguageStore {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (path: string) => string;
}

export const useLanguageStore = create<LanguageStore>()(
  persist(
    (set, get) => ({
      language: (localStorage.getItem('language') as Language) || 'tr', // Default to Turkish as requested
      setLanguage: (lang: Language) => {
        localStorage.setItem('language', lang);
        set({ language: lang });
      },
      t: (path: string) => {
        const keys = path.split('.');
        let current: any = translations[get().language];
        for (const key of keys) {
          if (current[key] === undefined) {
            // Fallback to English if key missing in Turkish
            let fallback: any = translations['en'];
            for (const fKey of keys) {
                if (fallback[fKey] === undefined) return path;
                fallback = fallback[fKey];
            }
            return fallback;
          }
          current = current[key];
        }
        return current;
      },
    }),
    {
      name: 'language-storage',
    }
  )
);
