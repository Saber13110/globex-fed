# Guide de modification rapide (fonctions + ou modifier)

Objectif: permettre a n'importe quel developpeur de modifier le projet rapidement.

## Comment utiliser ce fichier

1. Cherche ton besoin dans la section **"Je veux changer..."**.
2. Ouvre le(s) fichier(s) indique(s).
3. Modifie la fonction precise mentionnee.
4. Teste backend + frontend.

---

## 1) Je veux changer... (index rapide)

### Auth / Compte
- Login / Register:
  - Frontend: `frontend/src/app/features/auth/login/login.component.ts`, `register.component.ts`
  - Backend: `backend/app/routes/auth.py`
- Verification token utilisateur:
  - `backend/app/routes/deps.py` -> `get_current_user()`
- Logout all / delete account:
  - Frontend: `frontend/src/app/core/services/auth.service.ts`
  - Backend: `backend/app/routes/auth.py`

### Chat / Conversations
- Envoi d'un message:
  - Frontend: `frontend/src/app/core/services/chatbot.service.ts` -> `sendMessage()`
  - Backend: `backend/app/routes/chat.py` -> `post_message()`
- Liste des conversations:
  - Frontend: `frontend/src/app/core/services/chat-session.service.ts` -> `list()`
  - Backend: `backend/app/routes/chat.py` -> `list_sessions()`
- Renommer, pin/unpin, archiver, tags, deplacer dossier:
  - Frontend: `chat-page.component.ts` + `chat-item.component.ts`
  - Backend: `backend/app/routes/chat.py` -> `update_session()`
- Supprimer conversation:
  - Frontend: `chat-page.component.ts` -> `deleteSession()`
  - Backend: `backend/app/routes/chat.py` -> `delete_session()`

### Dossiers (projects / folders)
- Creer/lister dossiers:
  - Frontend: `chat-session.service.ts` -> `listCollections()`, `createCollection()`
  - Backend: `chat.py` -> `list_collections()`, `create_collection()`
- UI dossiers:
  - `frontend/src/app/features/chat/components/sidebar/sidebar.component.*`

### Partage de conversation
- Ouvrir modale share:
  - `chat-page.component.ts` -> `openShareModal()`
- Generer lien partage:
  - Frontend: `chat-page.component.ts` -> `generateShareLink()`
  - Service: `chat-session.service.ts` -> `createShareLink()`
  - Backend: `chat.py` -> `create_or_update_share_link()`
- Importer conversation partagee dans un autre compte:
  - Frontend: `chat-page.component.ts` -> `importSharedConversationFromToken()`
  - Service: `chat-session.service.ts` -> `importSharedConversation()`
  - Backend: `chat.py` -> `import_shared_conversation()`

### LLM (Qwen / Ollama)
- Changer modele:
  - `backend/.env` -> `LLM_MODEL=...`
  - `backend/app/core/config.py` -> valeur par defaut `llm_model`
- Prompt de reponse:
  - `backend/app/services/llm_service.py` -> `_build_prompt()`
- Prompt de titre conversation:
  - `backend/app/services/llm_service.py` -> `_build_title_prompt()`

### FedEx tracking
- Integration / appel API FedEx:
  - `backend/app/services/fedex_service.py`
- Endpoint tracking:
  - `backend/app/routes/tracking.py`
- Parsing numero suivi:
  - `backend/app/utils/tracking_parser.py`

### Theme, langue, preferences UI
- Preferences utilisateur (langue/theme/font/avatar):
  - `frontend/src/app/core/services/user-preferences.service.ts`
- Styles globaux:
  - `frontend/src/styles.scss`
- Parametres UI:
  - `frontend/src/app/features/settings/settings-page.component.*`

---

## 2) Fonctions backend importantes (et role)

## `backend/app/routes/chat.py`
- `post_message()`:
  - Recoit le message user, cree/recupere session, appelle `chatbot_service`.
- `list_sessions()`:
  - Retourne les conversations du user (avec filtres search/pinned/recent/etc).
- `get_session_messages()`:
  - Retourne les messages d'une session.
- `update_session()`:
  - Modifie titre, pin, archive, tags, dossier.
- `delete_session()`:
  - Supprime une session.
- `list_collections()` / `create_collection()`:
  - Gestion dossiers.
- `create_or_update_share_link()`:
  - Cree/maj token de partage.
- `get_shared_conversation()`:
  - Lit une conversation partagee.
- `import_shared_conversation()`:
  - Copie une conversation partagee dans le compte courant.

## `backend/app/services/chatbot_service.py`
- `process_user_message()`:
  - Orchestration principale chat:
    - parse message,
    - decide FedEx vs LLM,
    - enregistre messages en base.

## `backend/app/services/llm_service.py`
- `_build_prompt()`:
  - Construit le prompt principal du bot.
- `_build_title_prompt()`:
  - Construit le prompt de generation de titre.
- `generate_support_reply()`:
  - Appel Ollama `/api/generate`.
- `generate_session_title()`:
  - Generation titre intelligent.

## `backend/app/core/database.py`
- `init_db()`:
  - Creation tables + alter de colonnes si manquantes.
  - Point principal pour schema "dev simple".

## `backend/app/routes/deps.py`
- `get_current_user()`:
  - Validation JWT + validation session active.

---

## 3) Fonctions frontend importantes (et role)

## `frontend/src/app/features/chat/chat-page.component.ts`
- `ngOnInit()`:
  - Charge preferences, dossiers, sessions.
- `onSend(text)`:
  - Envoie message et met a jour l'UI.
- `openSession(session)`:
  - Charge les messages d'une conversation.
- `newConversation()`:
  - Reinitialise l'etat pour nouveau chat.
- `onSidebarRenameConversation()`:
  - Renomme conversation depuis sidebar.
- `onSidebarTogglePinConversation()`:
  - Pin/unpin depuis sidebar.
- `onSidebarMoveConversation()`:
  - Ouvre deplacement dossier.
- `openMoveModal()` / `moveToFolderFromModal()`:
  - Deplacement d'une conversation vers dossier.
- `openShareModal()` / `generateShareLink()`:
  - Partage conversation.
- `importSharedConversationFromToken(token)`:
  - Import automatique d'un lien partage.
- `loadSessions()`:
  - Recharge la liste conversations.

## `frontend/src/app/core/services/chat-session.service.ts`
- `list()`:
  - Lire conversations.
- `listMessages(sessionId)`:
  - Lire messages d'une session.
- `update(sessionId, payload)`:
  - Modifier une session (titre/pin/dossier/etc).
- `delete(sessionId)`:
  - Supprimer session.
- `listCollections()` / `createCollection()`:
  - Dossiers.
- `createShareLink()`:
  - Creer token partage.
- `importSharedConversation()`:
  - Import conversation partagee.

## `frontend/src/app/core/services/chatbot.service.ts`
- `sendMessage()`:
  - Appel API `/chat/message` avec contexte user.

## `frontend/src/app/core/services/user-preferences.service.ts`
- `read()`:
  - Lire prefs localStorage.
- `write()`:
  - Sauvegarder prefs.
- `applyToDocument()`:
  - Appliquer theme/langue/font au DOM.
- `syncFromAuthProfile()`:
  - Sync prefs depuis profil backend.

## `frontend/src/app/features/chat/components/chat-item/chat-item.component.ts`
- `startRename()` / `saveRename()`:
  - Rename inline.
- `onTogglePin()`:
  - Action pin/unpin.
- `onMove()`:
  - Action deplacer dossier.
- `onDelete()`:
  - Action suppression.

## `frontend/src/app/features/chat/components/share-conversation/share-conversation.component.ts`
- `copyLink()`:
  - Copie clipboard + etat "Lien copie".
- `onToggleIncludeTracking()`:
  - Toggle inclusion details tracking.

---

## 4) Regles simples pour modifier sans casser

1. **Changer une logique metier**:
   - backend d'abord (`routes` + `services` + `schemas`).
   - puis frontend (`services` + composants).

2. **Changer l'UI seulement**:
   - modifier `*.html` + `*.scss` du composant cible.
   - eviter de toucher le service si inutile.

3. **Ajouter un champ API**:
   - modele SQLAlchemy (si stocke en DB),
   - schema Pydantic,
   - route backend,
   - interface TS frontend,
   - affichage composant.

4. **Toujours verifier**:
   - backend: compilation Python ou lancement API.
   - frontend: `ng build`.

5. **Ne pas melanger**:
   - Dossiers = organisation.
   - Conversations = contenu principal.

---

## 5) Scenarios de modification frequents

### A) "Je veux changer le prompt LLM"
1. Ouvrir `backend/app/services/llm_service.py`.
2. Modifier `_build_prompt()`.
3. Redemarrer backend.

### B) "Je veux changer le style de la sidebar"
1. Ouvrir `frontend/src/app/features/chat/components/sidebar/sidebar.component.scss`.
2. Ajuster spacing/couleurs/hover.
3. Build frontend.

### C) "Je veux ajouter une action dans menu 3 points"
1. `chat-item.component.html` (ajouter bouton).
2. `chat-item.component.ts` (emitter action).
3. `chat-list.component.*` + `sidebar.component.*` (propager event).
4. `chat-page.component.ts` (traiter action).

### D) "Je veux changer le fonctionnement partage"
1. Backend `chat.py`:
   - `create_or_update_share_link()`
   - `import_shared_conversation()`
2. Frontend `chat-page.component.ts`:
   - `generateShareLink()`
   - `importSharedConversationFromToken()`

---

## 6) Mots-cles de recherche utiles

Utilise ces mots-cles dans la recherche IDE:
- `onSend(`
- `loadSessions(`
- `update_session(`
- `create_or_update_share_link(`
- `import_shared_conversation(`
- `generateShareLink(`
- `moveToFolderFromModal(`
- `_build_prompt(`
- `llm_model`
- `applyToDocument(`

---

Si besoin, je peux aussi te faire une version **encore plus orientee support equipe**:
- "Qui modifie quoi ?"
- "Risque de regression"
- "Checklist avant merge".
