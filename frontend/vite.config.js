import { defineConfig } from 'vite';
export default defineConfig({base:'/ui/',server:{proxy:Object.fromEntries(['/search','/pdf-documents','/me','/documents','/checklists','/audit','/health'].map(path=>[path,'http://127.0.0.1:8077']))}});
