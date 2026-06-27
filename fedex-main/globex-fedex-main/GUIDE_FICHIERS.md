# Guide des fichiers du projet

Ce document explique a quoi sert chaque fichier principal du projet `globex-fedex-chatbot`.

## 1) Racine du projet

- `GUIDE_FICHIERS.md` : ce guide de reference.
- `backend/` : API FastAPI + logique metier + acces base PostgreSQL.
- `frontend/` : application Angular 17 (UI, interactions utilisateur).

---

## 2) Backend (FastAPI)

### Dossier `backend/`

- `backend/.env` : variables d'environnement locales (DB, JWT, LLM, FedEx).
- `backend/.env.example` : modele d'exemple des variables d'environnement.
- `backend/requirements.txt` : dependances Python du backend.

### Dossier `backend/app/`

- `backend/app/main.py` : point d'entree FastAPI, CORS, startup DB, montage des routeurs.
- `backend/app/__init__.py` : marqueur de package Python.

### Dossier `backend/app/core/`

- `backend/app/core/config.py` : lecture centralisee de la configuration (`.env`).
- `backend/app/core/database.py` : connexion SQLAlchemy + initialisation/creation des tables.
- `backend/app/core/security.py` : hash password, creation/verification JWT.
- `backend/app/core/__init__.py` : package core.

### Dossier `backend/app/models/`

- `backend/app/models/base.py` : classe `Base` SQLAlchemy commune a tous les modeles.
- `backend/app/models/user.py` : modele utilisateur (identite, credentials, relations).
- `backend/app/models/user_session.py` : sessions de connexion actives par utilisateur.
- `backend/app/models/chat_session.py` : session de conversation (titre, pin, dossier, dates).
- `backend/app/models/chat_message.py` : messages d'une conversation (user/bot/system).
- `backend/app/models/chat_collection.py` : dossiers/projets pour organiser les conversations.
- `backend/app/models/shared_conversation_link.py` : tokens de partage de conversation entre comptes.
- `backend/app/models/tracking_request.py` : historique des demandes de tracking.
- `backend/app/models/shipment_cache.py` : cache local des resultats FedEx.
- `backend/app/models/__init__.py` : exports centralises des modeles.

### Dossier `backend/app/schemas/` (Pydantic)

- `backend/app/schemas/auth.py` : schemas des endpoints auth (login/register/token).
- `backend/app/schemas/user.py` : schemas profil utilisateur, overview compte/sessions.
- `backend/app/schemas/chat.py` : schemas chat, sessions, collections, partage.
- `backend/app/schemas/tracking.py` : schemas tracking FedEx/historique.
- `backend/app/schemas/__init__.py` : exports schemas.

### Dossier `backend/app/routes/` (API endpoints)

- `backend/app/routes/auth.py` : inscription, connexion, profil, logout, delete account.
- `backend/app/routes/deps.py` : dependances auth (`get_current_user`) et validation session.
- `backend/app/routes/chat.py` : messages chat, CRUD sessions, dossiers, partage/import.
- `backend/app/routes/tracking.py` : endpoints de tracking FedEx.
- `backend/app/routes/history.py` : endpoints de consultation historique.
- `backend/app/routes/export_excel.py` : export Excel des donnees/historique.
- `backend/app/routes/__init__.py` : package routes.

### Dossier `backend/app/services/` (logique metier)

- `backend/app/services/chatbot_service.py` : orchestration chat (message user -> reponse).
- `backend/app/services/llm_service.py` : appels Ollama/LLM (Qwen), prompts et titres auto.
- `backend/app/services/fedex_service.py` : integration API FedEx + normalisation des resultats.
- `backend/app/services/__init__.py` : package services.

### Dossier `backend/app/utils/`

- `backend/app/utils/tracking_parser.py` : extraction/validation numero de suivi depuis texte.
- `backend/app/utils/__init__.py` : package utils.

---

## 3) Frontend (Angular 17)

### Dossier `frontend/src/app/`

- `frontend/src/app/app.component.ts` : composant racine Angular.
- `frontend/src/app/app.component.html` : template racine.
- `frontend/src/app/app.component.spec.ts` : test unitaire racine.
- `frontend/src/app/app.config.ts` : providers globaux Angular.
- `frontend/src/app/app.routes.ts` : routing principal (login/register/chat/history/settings/shared).

### Dossier `frontend/src/app/core/`

#### Config API
- `frontend/src/app/core/api.config.ts` : URL API backend + cle de stockage token.

#### Services
- `frontend/src/app/core/services/auth.service.ts` : auth frontend (login/register/me/logout/account).
- `frontend/src/app/core/services/chatbot.service.ts` : envoi message chat (`/chat/message`).
- `frontend/src/app/core/services/chat-session.service.ts` : sessions chat, collections, partage/import.
- `frontend/src/app/core/services/history.service.ts` : appels API historique.
- `frontend/src/app/core/services/tracking.service.ts` : appels API tracking.
- `frontend/src/app/core/services/user-preferences.service.ts` : preferences UI/langue/theme/avatar.

#### Guards
- `frontend/src/app/core/guards/auth.guard.ts` : protege les routes privees.
- `frontend/src/app/core/guards/guest.guard.ts` : bloque pages auth si deja connecte.

#### Interceptor
- `frontend/src/app/core/interceptors/auth.interceptor.ts` : injecte le JWT dans les requetes HTTP.

### Dossier `frontend/src/app/features/auth/`

- `frontend/src/app/features/auth/login/login.component.ts` : logique page login.
- `frontend/src/app/features/auth/login/login.component.html` : template login.
- `frontend/src/app/features/auth/login/login.component.scss` : styles login.
- `frontend/src/app/features/auth/register/register.component.ts` : logique page inscription.
- `frontend/src/app/features/auth/register/register.component.html` : template inscription.
- `frontend/src/app/features/auth/register/register.component.scss` : styles inscription.

### Dossier `frontend/src/app/features/chat/`

- `frontend/src/app/features/chat/chat-page.component.ts` : orchestrateur principal de l'UI chat.
- `frontend/src/app/features/chat/chat-page.component.html` : layout global (sidebar + zone chat + modales).
- `frontend/src/app/features/chat/chat-page.component.scss` : styles globaux de la page chat.

#### Sous-composants chat

- `frontend/src/app/features/chat/components/sidebar/sidebar.component.ts` : logique sidebar (sections, events).
- `frontend/src/app/features/chat/components/sidebar/sidebar.component.html` : structure sidebar.
- `frontend/src/app/features/chat/components/sidebar/sidebar.component.scss` : styles sidebar.

- `frontend/src/app/features/chat/components/chat-list/chat-list.component.ts` : liste reutilisable de conversations.
- `frontend/src/app/features/chat/components/chat-list/chat-list.component.html` : rendu d'une section de liste.
- `frontend/src/app/features/chat/components/chat-list/chat-list.component.scss` : styles de liste.

- `frontend/src/app/features/chat/components/chat-item/chat-item.component.ts` : item conversation + actions (rename/pin/move/delete).
- `frontend/src/app/features/chat/components/chat-item/chat-item.component.html` : template item + menu 3 points.
- `frontend/src/app/features/chat/components/chat-item/chat-item.component.scss` : styles item + etats hover/active.

- `frontend/src/app/features/chat/components/chat-header/chat-header.component.ts` : header de conversation (titre, share, menu).
- `frontend/src/app/features/chat/components/chat-header/chat-header.component.html` : template header.
- `frontend/src/app/features/chat/components/chat-header/chat-header.component.scss` : styles header.

- `frontend/src/app/features/chat/components/share-conversation/share-conversation.component.ts` : modale partage + copie lien.
- `frontend/src/app/features/chat/components/share-conversation/share-conversation.component.html` : template modale partage.
- `frontend/src/app/features/chat/components/share-conversation/share-conversation.component.scss` : styles modale partage.

- `frontend/src/app/features/chat/components/chat-input/chat-input.component.ts` : barre de saisie (hero/dock).
- `frontend/src/app/features/chat/components/chat-input/chat-input.component.html` : template input.
- `frontend/src/app/features/chat/components/chat-input/chat-input.component.scss` : styles input.

- `frontend/src/app/features/chat/components/message-list/message-list.component.ts` : affichage de la liste de messages.
- `frontend/src/app/features/chat/components/message-list/message-list.component.html` : template messages (user/bot/source).
- `frontend/src/app/features/chat/components/message-list/message-list.component.scss` : styles bulles/messages.

### Dossier `frontend/src/app/features/history/`

- `frontend/src/app/features/history/history-page.component.ts` : logique page historique.
- `frontend/src/app/features/history/history-page.component.html` : template historique.
- `frontend/src/app/features/history/history-page.component.scss` : styles historique.

### Dossier `frontend/src/app/features/settings/`

- `frontend/src/app/features/settings/settings-page.component.ts` : logique parametres (general/compte/etc.).
- `frontend/src/app/features/settings/settings-page.component.html` : template parametres.
- `frontend/src/app/features/settings/settings-page.component.scss` : styles parametres.

### Dossier `frontend/src/app/shared/`

- `frontend/src/app/shared/fedex-workspace-shell.scss` : styles shell global (grille workspace/sidebar/canvas).

#### Components partages
- `frontend/src/app/shared/components/shipment-card/shipment-card.component.ts` : carte resume shipment.
- `frontend/src/app/shared/components/shipment-card/shipment-card.component.html` : template carte shipment.
- `frontend/src/app/shared/components/shipment-card/shipment-card.component.scss` : styles carte shipment.

---

## 4) Fichiers importants hors `src/app`

- `frontend/src/styles.scss` : styles globaux de toute l'app (theme/light-dark/font/motion).

---

## 5) Remarques

- Ce guide couvre les fichiers metier/produit principaux.
- Les fichiers de venv, cache, build (`.venv`, `__pycache__`, `dist`, etc.) ne sont pas documentes ici.
- Si tu veux, je peux aussi te generer une version **detaillee par flux** :
  - flux login,
  - flux chat,
  - flux partage,
  - flux dossiers/projets,
  - flux FedEx tracking.
