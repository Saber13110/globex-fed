--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.activity_logs (
    id integer NOT NULL,
    user_id integer,
    actor_user_id integer,
    level character varying(16) NOT NULL,
    category character varying(32) NOT NULL,
    action character varying(64) NOT NULL,
    message text NOT NULL,
    metadata_json text NOT NULL,
    ip_address character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.activity_logs OWNER TO postgres;

--
-- Name: activity_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.activity_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.activity_logs_id_seq OWNER TO postgres;

--
-- Name: activity_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.activity_logs_id_seq OWNED BY public.activity_logs.id;


--
-- Name: chat_collections; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chat_collections (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(120) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.chat_collections OWNER TO postgres;

--
-- Name: chat_collections_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chat_collections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chat_collections_id_seq OWNER TO postgres;

--
-- Name: chat_collections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chat_collections_id_seq OWNED BY public.chat_collections.id;


--
-- Name: chat_messages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chat_messages (
    id integer NOT NULL,
    session_id integer NOT NULL,
    sender character varying(16) NOT NULL,
    message_text text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    source character varying(32) DEFAULT 'unknown'::character varying NOT NULL
);


ALTER TABLE public.chat_messages OWNER TO postgres;

--
-- Name: chat_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chat_messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chat_messages_id_seq OWNER TO postgres;

--
-- Name: chat_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chat_messages_id_seq OWNED BY public.chat_messages.id;


--
-- Name: chat_sessions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chat_sessions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    title character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    is_pinned boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_archived boolean DEFAULT false NOT NULL,
    tags text DEFAULT ''::text NOT NULL,
    collection_id integer
);


ALTER TABLE public.chat_sessions OWNER TO postgres;

--
-- Name: chat_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chat_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chat_sessions_id_seq OWNER TO postgres;

--
-- Name: chat_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chat_sessions_id_seq OWNED BY public.chat_sessions.id;


--
-- Name: login_otp_challenges; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.login_otp_challenges (
    id integer NOT NULL,
    user_id integer NOT NULL,
    challenge_token character varying(96) NOT NULL,
    otp_hash character varying(255) NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    last_sent_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.login_otp_challenges OWNER TO postgres;

--
-- Name: login_otp_challenges_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.login_otp_challenges_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.login_otp_challenges_id_seq OWNER TO postgres;

--
-- Name: login_otp_challenges_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.login_otp_challenges_id_seq OWNED BY public.login_otp_challenges.id;


--
-- Name: preference_submissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.preference_submissions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    proposed_text text NOT NULL,
    status character varying(20) NOT NULL,
    risk_score integer NOT NULL,
    risk_reasons text NOT NULL,
    rejection_note character varying(500) NOT NULL,
    reviewed_by integer,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    structured_json text DEFAULT '{}'::text NOT NULL
);


ALTER TABLE public.preference_submissions OWNER TO postgres;

--
-- Name: preference_submissions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.preference_submissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.preference_submissions_id_seq OWNER TO postgres;

--
-- Name: preference_submissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.preference_submissions_id_seq OWNED BY public.preference_submissions.id;


--
-- Name: shared_conversation_links; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shared_conversation_links (
    id integer NOT NULL,
    session_id integer NOT NULL,
    owner_user_id integer NOT NULL,
    share_token character varying(96) NOT NULL,
    include_tracking_details boolean NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.shared_conversation_links OWNER TO postgres;

--
-- Name: shared_conversation_links_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.shared_conversation_links_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.shared_conversation_links_id_seq OWNER TO postgres;

--
-- Name: shared_conversation_links_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.shared_conversation_links_id_seq OWNED BY public.shared_conversation_links.id;


--
-- Name: shipment_cache; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shipment_cache (
    id integer NOT NULL,
    tracking_number character varying(64) NOT NULL,
    raw_response_json text NOT NULL,
    last_status character varying(128),
    last_location character varying(255),
    estimated_delivery character varying(64),
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.shipment_cache OWNER TO postgres;

--
-- Name: shipment_cache_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.shipment_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.shipment_cache_id_seq OWNER TO postgres;

--
-- Name: shipment_cache_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.shipment_cache_id_seq OWNED BY public.shipment_cache.id;


--
-- Name: support_tickets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.support_tickets (
    id integer NOT NULL,
    user_id integer NOT NULL,
    subject character varying(200) NOT NULL,
    message text NOT NULL,
    status character varying(20) NOT NULL,
    admin_note character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.support_tickets OWNER TO postgres;

--
-- Name: support_tickets_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.support_tickets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.support_tickets_id_seq OWNER TO postgres;

--
-- Name: support_tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.support_tickets_id_seq OWNED BY public.support_tickets.id;


--
-- Name: tracking_requests; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tracking_requests (
    id integer NOT NULL,
    user_id integer NOT NULL,
    tracking_number character varying(64) NOT NULL,
    user_question text NOT NULL,
    bot_response text NOT NULL,
    status character varying(128),
    current_location character varying(255),
    estimated_delivery character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    session_id integer
);


ALTER TABLE public.tracking_requests OWNER TO postgres;

--
-- Name: tracking_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tracking_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tracking_requests_id_seq OWNER TO postgres;

--
-- Name: tracking_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tracking_requests_id_seq OWNED BY public.tracking_requests.id;


--
-- Name: user_sessions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_sessions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    token_id character varying(64) NOT NULL,
    browser character varying(80) NOT NULL,
    machine character varying(80) NOT NULL,
    location character varying(120) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.user_sessions OWNER TO postgres;

--
-- Name: user_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_sessions_id_seq OWNER TO postgres;

--
-- Name: user_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_sessions_id_seq OWNED BY public.user_sessions.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    full_name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role character varying(32) NOT NULL,
    preferred_language character varying(8) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    organization_id character varying(64),
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    activation_token character varying(96),
    activation_expires_at timestamp with time zone,
    qr_login_token_digest character varying(64),
    response_preferences text DEFAULT ''::text NOT NULL,
    quota_messages_per_day integer,
    quota_trackings_per_day integer,
    quota_exports_per_day integer,
    preference_profile_json text DEFAULT '{}'::text NOT NULL
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: activity_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activity_logs ALTER COLUMN id SET DEFAULT nextval('public.activity_logs_id_seq'::regclass);


--
-- Name: chat_collections id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_collections ALTER COLUMN id SET DEFAULT nextval('public.chat_collections_id_seq'::regclass);


--
-- Name: chat_messages id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_messages ALTER COLUMN id SET DEFAULT nextval('public.chat_messages_id_seq'::regclass);


--
-- Name: chat_sessions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_sessions ALTER COLUMN id SET DEFAULT nextval('public.chat_sessions_id_seq'::regclass);


--
-- Name: login_otp_challenges id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.login_otp_challenges ALTER COLUMN id SET DEFAULT nextval('public.login_otp_challenges_id_seq'::regclass);


--
-- Name: preference_submissions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.preference_submissions ALTER COLUMN id SET DEFAULT nextval('public.preference_submissions_id_seq'::regclass);


--
-- Name: shared_conversation_links id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shared_conversation_links ALTER COLUMN id SET DEFAULT nextval('public.shared_conversation_links_id_seq'::regclass);


--
-- Name: shipment_cache id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment_cache ALTER COLUMN id SET DEFAULT nextval('public.shipment_cache_id_seq'::regclass);


--
-- Name: support_tickets id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.support_tickets ALTER COLUMN id SET DEFAULT nextval('public.support_tickets_id_seq'::regclass);


--
-- Name: tracking_requests id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tracking_requests ALTER COLUMN id SET DEFAULT nextval('public.tracking_requests_id_seq'::regclass);


--
-- Name: user_sessions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_sessions ALTER COLUMN id SET DEFAULT nextval('public.user_sessions_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: activity_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.activity_logs (id, user_id, actor_user_id, level, category, action, message, metadata_json, ip_address, created_at) FROM stdin;
1	10	\N	SUCCESS	auth	auth.login	Connexion réussie (employe)	{"browser": "Edge", "machine": "Windows"}	127.0.0.1	2026-06-01 19:30:38.938022+02
2	10	\N	SUCCESS	auth	auth.login	Connexion réussie (employe)	{"browser": "Edge", "machine": "Windows"}	127.0.0.1	2026-06-01 19:31:00.913305+02
3	10	\N	INFO	chat	chat.user_message	Prompt : bonjour	{"session_id": 33, "has_image": false}	127.0.0.1	2026-06-01 19:31:08.626946+02
5	6	\N	SUCCESS	auth	auth.login	Connexion réussie (admin)	{"browser": "Edge", "machine": "Windows"}	127.0.0.1	2026-06-01 19:31:28.737355+02
6	6	\N	SUCCESS	auth	auth.login	Connexion réussie (admin)	{"browser": "Edge", "machine": "Windows", "method": "password"}	127.0.0.1	2026-06-01 19:49:10.334101+02
7	12	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : elhajbinourelhouda@gmail.com	{}	127.0.0.1	2026-06-01 19:49:19.361413+02
8	12	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : elhajbinourelhouda@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-01 19:49:19.443677+02
9	10	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : sxr2123@gmail.com	{}	127.0.0.1	2026-06-01 19:49:41.526495+02
10	10	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : sxr2123@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-01 19:49:41.58703+02
11	12	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : elhajbinourelhouda@gmail.com	{}	127.0.0.1	2026-06-01 20:19:29.449458+02
12	12	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : elhajbinourelhouda@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-01 20:19:29.553218+02
13	12	6	INFO	admin	admin.user_update	Profil modifié par admin (quota messages/j, quota suivis/j, quota exports/j) : elhajbinourelhouda@gmail.com	{"fields": ["quota messages/j", "quota suivis/j", "quota exports/j"]}	127.0.0.1	2026-06-01 20:19:59.839544+02
14	12	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : elhajbinourelhouda@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-01 20:20:00.069347+02
15	12	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : elhajbinourelhouda@gmail.com	{}	127.0.0.1	2026-06-01 21:54:19.701627+02
16	12	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : elhajbinourelhouda@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-01 21:54:19.781248+02
17	12	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : elhajbinourelhouda@gmail.com	{}	127.0.0.1	2026-06-01 21:54:39.982898+02
18	12	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : elhajbinourelhouda@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-01 21:54:40.045599+02
19	12	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : elhajbinourelhouda@gmail.com	{}	127.0.0.1	2026-06-02 02:22:49.588097+02
20	12	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : elhajbinourelhouda@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-02 02:22:49.71136+02
21	6	\N	SUCCESS	auth	auth.login	Connexion réussie (admin)	{"browser": "Unknown", "machine": "Unknown", "method": "password"}	127.0.0.1	2026-06-02 02:31:31.085362+02
22	6	\N	INFO	system	export.tracking_excel	Export Excel historique suivi (0 lignes)	{"row_count": 0, "limit": 5, "lang": "fr", "columns": "id,tracking_number,user_question,bot_response,status,current_location,estimated_delivery,created_at", "include_events": false}	127.0.0.1	2026-06-02 02:31:31.908615+02
23	12	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : elhajbinourelhouda@gmail.com	{}	127.0.0.1	2026-06-02 03:24:55.190469+02
24	12	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : elhajbinourelhouda@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-02 03:24:55.333548+02
25	6	\N	SUCCESS	auth	auth.login	Connexion réussie (admin)	{"browser": "Unknown", "machine": "Unknown", "method": "password"}	127.0.0.1	2026-06-02 03:42:10.521533+02
26	6	\N	INFO	system	export.tracking_excel	Export Excel historique suivi (0 lignes)	{"row_count": 0, "limit": 5, "lang": "fr", "columns": "id,tracking_number,user_question,bot_response,status,current_location,estimated_delivery,created_at", "include_events": false}	127.0.0.1	2026-06-02 03:42:11.948823+02
27	6	\N	SUCCESS	auth	auth.login	Connexion réussie (admin)	{"browser": "Edge", "machine": "Windows", "method": "password"}	127.0.0.1	2026-06-02 05:20:36.265644+02
28	5	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : amine@gmail.com	{}	127.0.0.1	2026-06-02 05:20:44.291575+02
29	5	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : amine@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-02 05:20:44.46354+02
30	10	6	INFO	admin	admin.user_view	Fiche utilisateur consultée : sxr2123@gmail.com	{}	127.0.0.1	2026-06-02 05:20:58.362784+02
31	10	6	INFO	admin	admin.logs_view	Consultation journaux utilisateur : sxr2123@gmail.com	{"filters": {"category": null, "level": null, "q": null}}	127.0.0.1	2026-06-02 05:20:58.44018+02
\.


--
-- Data for Name: chat_collections; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.chat_collections (id, user_id, name, created_at) FROM stdin;
1	3	tgerge	2026-04-28 20:12:29.895671+02
2	4	gzuhjk	2026-04-28 22:18:50.439734+02
3	5	dossier1	2026-05-26 20:34:33.43446+02
4	5	doss	2026-05-31 16:45:11.881116+02
\.


--
-- Data for Name: chat_messages; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.chat_messages (id, session_id, sender, message_text, created_at, source) FROM stdin;
1	1	user	bonjour	2026-04-22 03:20:00.281883+02	unknown
2	1	bot	Je n’ai pas détecté de numéro de suivi FedEx dans votre message. Merci d’indiquer un numéro valide (par exemple 12 ou 14 chiffres).	2026-04-22 03:20:00.281883+02	unknown
3	1	user	ou est mon coulis 1223874384713	2026-04-22 03:20:14.174462+02	unknown
4	1	bot	Voici le suivi pour le colis **1223874384713**.\n- Statut : En transit\n- Localisation : Hub Casablanca\n- Livraison estimée : 2026-04-25	2026-04-22 03:20:14.174462+02	unknown
5	2	user	bonjour	2026-04-22 03:34:58.204005+02	unknown
6	2	bot	Je n’ai pas détecté de numéro de suivi FedEx dans votre message. Merci d’indiquer un numéro valide (par exemple 12 ou 14 chiffres).	2026-04-22 03:34:58.204005+02	unknown
7	2	user	bonjour	2026-04-22 03:35:12.240799+02	unknown
8	2	bot	Je n’ai pas détecté de numéro de suivi FedEx dans votre message. Merci d’indiquer un numéro valide (par exemple 12 ou 14 chiffres).	2026-04-22 03:35:12.240799+02	unknown
47	16	user	dhbn	2026-04-28 21:22:04.984125+02	user_input
48	16	bot	Je n’ai pas détecté de numéro de suivi FedEx dans votre message. Merci d’indiquer un numéro valide (par exemple 12 ou 14 chiffres).	2026-04-28 21:22:04.984125+02	fallback
49	17	user	Où est mon colis 123456789012 ?	2026-04-28 21:22:30.053998+02	user_input
50	17	bot	Voici le suivi pour le colis **123456789012**.\n- Statut : Ready for pickup\n- Localisation : GREENWOOD, United States\n- Livraison estimée : N/A	2026-04-28 21:22:30.053998+02	fedex_api
51	18	user	bonjour	2026-04-28 22:13:24.264328+02	user_input
52	18	bot	Je n’ai pas détecté de numéro de suivi FedEx dans votre message. Merci d’indiquer un numéro valide (par exemple 12 ou 14 chiffres).	2026-04-28 22:13:24.264328+02	fallback
53	19	user	dhbn	2026-04-28 22:18:16.843353+02	user_input
54	19	bot	Je n’ai pas détecté de numéro de suivi FedEx dans votre message. Merci d’indiquer un numéro valide (par exemple 12 ou 14 chiffres).	2026-04-28 22:18:16.843353+02	fallback
55	20	user	Où est mon colis 123456789012 ?	2026-04-29 00:00:30.541708+02	user_input
56	20	bot	Voici le suivi pour le colis **123456789012**.\n- Statut : Ready for pickup\n- Localisation : GREENWOOD, United States\n- Livraison estimée : N/A	2026-04-29 00:00:30.541708+02	fedex_api
57	21	user	Où est mon colis 123456789012 ?	2026-05-26 20:35:20.074505+02	user_input
58	22	user	qqwwerr	2026-05-26 20:35:49.31212+02	user_input
59	21	bot	Voici le suivi pour le colis **123456789012**.\n- Statut : Ready for pickup\n- Localisation : GREENWOOD, United States\n- Livraison estimée : N/A	2026-05-26 20:35:20.074505+02	fedex_api
60	22	bot	Bonjour Ana,\n\nJe vous remercie pour votre message. Il semble que vous ayez entré une séquence aléatoire de caractères. Pourriez-vous me donner plus d'informations ou le numéro de suivi FedEx si vous avez un, afin que je puisse vérifier l'état de votre colis ?\n\nN'hésitez pas à me contacter si vous avez des questions supplémentaires.\n\nCordialement,\n[Votre nom] - Assistant FedEx	2026-05-26 20:35:49.31212+02	llm
61	23	user	Exporte mon historique de tracking en Excel	2026-05-31 17:33:19.772549+02	user_input
62	23	bot	J'ai prepare l'export Excel de votre historique. Cliquez ici : http://127.0.0.1:8000/export/tracking-history.xlsx?limit=200	2026-05-31 17:33:19.772549+02	export
63	24	user	Où est mon colis 123456789012 ?	2026-05-31 20:28:21.445304+02	user_input
64	24	bot	Voici le suivi pour le colis **123456789012**.\n- Statut : Ready for pickup\n- Localisation : GREENWOOD, United States\n- Livraison estimée : N/A	2026-05-31 20:28:21.445304+02	fedex_api
65	25	user	bonjour	2026-06-01 16:32:59.412017+02	user_input
66	25	bot	Je n'ai pas détecté de numéro de suivi FedEx dans votre message. Merci d'indiquer un numéro valide (par exemple 12 ou 14 chiffres).	2026-06-01 16:32:59.412017+02	fallback
67	25	user	bonjour	2026-06-01 16:34:03.467116+02	user_input
68	25	bot	Je n'ai pas détecté de numéro de suivi FedEx dans votre message. Merci d'indiquer un numéro valide (par exemple 12 ou 14 chiffres).	2026-06-01 16:34:03.467116+02	fallback
69	26	user	bonjour	2026-06-01 16:44:25.080168+02	user_input
70	26	bot	Hello Ana!\n\nI'm your intelligent assistant specialized in FedEx package tracking. I can help you understand your package's status, prepare an Excel export, explain a proof of delivery, or answer any general questions you might have about tracking.\n\nPlease note that I don't have any real FedEx data available at the moment, so I cannot confirm any specific status, delivery date, or location without that information.\n\nHow can I assist you today?	2026-06-01 16:44:25.080168+02	gemini
71	26	user	bonjour	2026-06-01 16:46:30.146172+02	user_input
72	26	bot	Hello Ana!\n\nI'm your intelligent assistant specialized in FedEx package tracking. I can help you understand your package's status, prepare an Excel export, explain a proof of delivery, or answer any general questions you might have about tracking.\n\nPlease note that I don't have any real FedEx data available at the moment, so I won't be able to confirm any specific status, delivery dates, or locations until you provide me with a tracking number or more details.\n\nHow can I assist you today?	2026-06-01 16:46:30.146172+02	gemini
73	27	user	bonjour	2026-06-01 16:51:09.725632+02	user_input
74	27	bot	Hello there! My name is here to assist you with your FedEx tracking inquiries. \n\nHow can I help you today, ana? Do you have a tracking number you’d like to check, or perhaps a general question about FedEx tracking in general?	2026-06-01 16:51:09.725632+02	ollama
75	27	user	bonjour	2026-06-01 16:53:28.669064+02	user_input
76	27	bot	Hello Ana! I'm your FedEx package tracking assistant. How can I help you today? Please provide me with a tracking number or tell me what you'd like to know about FedEx tracking.	2026-06-01 16:53:28.669064+02	gemini
77	27	user	en francais	2026-06-01 16:53:40.062823+02	user_input
78	27	bot	Hello Ana,\n\nI understand you'd like to communicate in French. However, I am programmed to respond only in English.\n\nHow can I assist you today with your FedEx package tracking?	2026-06-01 16:53:40.062823+02	gemini
79	28	user	bonjour	2026-06-01 16:58:25.745855+02	user_input
80	28	bot	Hello Ana!\n\nI'm a specialized intelligent assistant for FedEx package tracking. I can help you understand your package status, prepare an Excel export, explain a proof of delivery, answer general tracking questions, and guide you through the process.\n\nPlease note that I don't have any specific FedEx data available right now, so I can't confirm any status, delivery date, or location without real FedEx information.\n\nHow can I assist you today?	2026-06-01 16:58:25.745855+02	gemini
83	30	user	bonjour	2026-06-01 17:05:12.751201+02	user_input
84	30	bot	Bonjour ana,\n\nComment puis-je vous aider aujourd'hui concernant le suivi de vos colis FedEx ?	2026-06-01 17:05:12.751201+02	gemini
85	30	user	je veux suivre un colis	2026-06-01 17:05:29.497936+02	user_input
86	30	bot	Bonjour ana,\n\nJe suis là pour vous aider à suivre votre colis FedEx. Cependant, je n'ai pas reçu les informations nécessaires pour effectuer le suivi.\n\nPourriez-vous s'il vous plaît me fournir le numéro de suivi de votre colis ? Une fois que j'aurai ce numéro, je pourrai vous aider à obtenir les informations les plus récentes sur son statut.	2026-06-01 17:05:29.497936+02	gemini
87	31	user	bonjour	2026-06-01 17:32:24.826711+02	user_input
88	31	bot	Bonjour ana,\n\nComment puis-je vous aider aujourd'hui concernant le suivi de vos colis FedEx ?	2026-06-01 17:32:24.826711+02	gemini
89	32	user	bonjour	2026-06-01 18:31:36.76057+02	user_input
90	32	bot	Bonjour ana,\n\nComment puis-je vous aider aujourd'hui concernant le suivi de vos colis FedEx ?	2026-06-01 18:31:36.76057+02	gemini
91	33	user	bonjour	2026-06-01 19:31:08.626946+02	user_input
92	33	bot	Bonjour ana,\n\nComment puis-je vous aider aujourd'hui concernant le suivi de vos colis FedEx ?	2026-06-01 19:31:08.626946+02	gemini
\.


--
-- Data for Name: chat_sessions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.chat_sessions (id, user_id, title, created_at, is_pinned, updated_at, is_archived, tags, collection_id) FROM stdin;
1	1	bonjour	2026-04-22 03:20:00.281883+02	f	2026-04-28 05:52:10.73459+02	f		\N
2	1	bonjour	2026-04-22 03:34:58.204005+02	f	2026-04-28 05:52:10.73459+02	f		\N
30	10	Suivi colis FedEx	2026-06-01 17:05:12.751201+02	f	2026-06-01 17:05:29.497936+02	f		\N
31	10	Suivi colis FedEx	2026-06-01 17:32:24.826711+02	f	2026-06-01 17:32:24.826711+02	f		\N
32	10	Suivi colis FedEx	2026-06-01 18:31:36.76057+02	f	2026-06-01 18:31:36.76057+02	f		\N
33	10	Assistance suivi FedEx	2026-06-01 19:31:08.626946+02	f	2026-06-01 19:31:08.626946+02	f		\N
16	3	dhbn	2026-04-28 21:22:04.984125+02	f	2026-04-28 21:22:11.29955+02	f		1
17	3	Où est mon colis 123456789012 ?	2026-04-28 21:22:30.053998+02	f	2026-04-28 21:22:30.053998+02	f		\N
19	4	dhbn (partagé)	2026-04-28 22:18:16.843353+02	f	2026-04-28 22:18:55.109094+02	f		\N
18	4	bonjour	2026-04-28 22:13:24.264328+02	f	2026-04-28 22:42:17.002081+02	f		2
20	4	Suivi colis USA	2026-04-29 00:00:30.541708+02	f	2026-04-29 00:00:30.541708+02	f		\N
21	5	Suivi colis USA	2026-05-26 20:35:20.074505+02	f	2026-05-26 20:35:20.074505+02	f		\N
22	5	État de colis FedEx	2026-05-26 20:35:49.31212+02	f	2026-05-26 20:35:49.31212+02	f		\N
23	7	Nouvelle conversation	2026-05-31 17:33:19.772549+02	f	2026-05-31 17:33:19.772549+02	f		\N
24	10	Suivi colis USA	2026-05-31 20:28:21.445304+02	f	2026-06-01 15:39:59.898679+02	f		\N
25	10	bonjour	2026-06-01 16:32:59.412017+02	f	2026-06-01 16:34:03.467116+02	f		\N
26	10	FedEx Package Tracking Assistant - Questions & Status	2026-06-01 16:44:25.080168+02	f	2026-06-01 16:46:30.146172+02	f		\N
27	10	FedEx	2026-06-01 16:51:09.725632+02	f	2026-06-01 16:53:40.062823+02	f		\N
28	10	Fed	2026-06-01 16:58:25.745855+02	f	2026-06-01 16:58:25.745855+02	f		\N
\.


--
-- Data for Name: login_otp_challenges; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.login_otp_challenges (id, user_id, challenge_token, otp_hash, attempts, expires_at, last_sent_at, created_at) FROM stdin;
3	6	ikVf2ehb0eXz0d0TJ6htQL11Jy6ppMWV-hlc3YfZ8Lw	$2b$12$QoWThYkgTk4s6UVzuXaYVuiIltVE9va7hsqdxmC7oVqVsLiTqeArm	0	2026-05-31 19:57:12.273216+02	2026-05-31 19:47:12.273237+02	2026-05-31 19:47:11.245804+02
\.


--
-- Data for Name: preference_submissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.preference_submissions (id, user_id, proposed_text, status, risk_score, risk_reasons, rejection_note, reviewed_by, reviewed_at, created_at, structured_json) FROM stdin;
\.


--
-- Data for Name: shared_conversation_links; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.shared_conversation_links (id, session_id, owner_user_id, share_token, include_tracking_details, is_active, created_at, updated_at) FROM stdin;
1	16	3	wKmkc8jTwMnFyntIwnsHoQNUR4BOZ6MN	f	t	2026-04-28 22:17:21.144132+02	2026-04-28 22:17:21.144132+02
2	20	4	9ACxtSh6W9vRt8VuNZCU67AH5adBiKFW	f	t	2026-04-29 00:01:51.003211+02	2026-04-29 00:01:51.003211+02
3	18	4	WtG1h1_audjxqUEWrlbZi8mpCqGaslz5	f	t	2026-04-29 00:40:17.218616+02	2026-04-29 00:40:17.218616+02
4	24	10	hLJTid4EPiJQTlpqcCKlV3Vzw11sWsqR	f	t	2026-05-31 21:24:57.019943+02	2026-05-31 21:24:57.019943+02
\.


--
-- Data for Name: shipment_cache; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.shipment_cache (id, tracking_number, raw_response_json, last_status, last_location, estimated_delivery, updated_at) FROM stdin;
1	1223874384713	{"tracking_number": "1223874384713", "status": "En transit", "current_location": "Hub Casablanca", "estimated_delivery": "2026-04-25", "events": [{"at": "2026-04-21T10:00:00Z", "description": "Colis reçu au hub", "location": "Casablanca"}, {"at": "2026-04-20T18:30:00Z", "description": "En route vers destination", "location": "Paris"}], "source": "mock_fedex"}	En transit	Hub Casablanca	2026-04-25	2026-04-22 03:20:14.174462+02
2	772254547006	{"tracking_number": "772254547006", "status": "Ready for pickup", "current_location": "GREENWOOD, United States", "estimated_delivery": "N/A", "events": [{"at": "2023-05-19T19:03:00-04:00", "description": "Ready for recipient pickup", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T08:25:00-04:00", "description": "On FedEx vehicle for delivery", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T07:31:24-04:00", "description": "Hold at location request accepted", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T07:31:00-04:00", "description": "Arrived at FedEx location", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T05:11:00-04:00", "description": "At local FedEx facility", "location": "GREENWOOD, United States"}, {"at": "2023-05-18T15:50:00-04:00", "description": "Arrived at FedEx location", "location": "GREENWOOD, United States"}, {"at": "2023-05-18T04:21:19-07:00", "description": "Departed FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-18T02:57:54-05:00", "description": "In transit", "location": "UTICA, United States"}, {"at": "2023-05-17T17:03:23-04:00", "description": "Delivery option requested", "location": "United States"}, {"at": "2023-05-17T13:48:44-06:00", "description": "In transit", "location": "LARAMIE, United States"}, {"at": "2023-05-17T01:47:24-06:00", "description": "In transit", "location": "KING HILL, United States"}, {"at": "2023-05-16T12:47:07-07:00", "description": "Departed FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T21:47:26-07:00", "description": "Shipment arriving On-Time", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T21:46:00-07:00", "description": "Arrived at FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T17:15:00-07:00", "description": "Picked up", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T13:29:00-07:00", "description": "Shipment information sent to FedEx", "location": "United States"}], "source": "fedex_api", "raw": {"transactionId": "APIF_SV_TRKC_TxIDAPIF_SV_TxID18a9b1a3-6749-4e81-b985-fd49ba83c00f", "customertransactionId": "APIF_SV_TRKC_TxIDcustomer test", "output": {"alerts": [{"code": "VIRTUAL.RESPONSE", "message": "This is a Virtual Response."}], "completeTrackResults": [{"trackingNumber": "772254547006", "trackResults": [{"trackingNumberInfo": {"trackingNumber": "772254547006", "trackingNumberUniqueId": "12025~772254547006~FDEG", "carrierCode": "FDXG"}, "additionalTrackingInfo": {"nickname": "", "packageIdentifiers": [{"type": "PURCHASE_ORDER", "values": ["1683571649"], "trackingNumberUniqueId": "", "carrierCode": ""}, {"type": "INVOICE", "values": ["30186971"], "trackingNumberUniqueId": "", "carrierCode": ""}], "hasAssociatedShipments": false}, "shipperInformation": {"contact": {}, "address": {"city": "Vancouver", "stateOrProvinceCode": "WA", "countryCode": "US", "residential": false, "countryName": "United States"}}, "recipientInformation": {"contact": {}, "address": {"city": "Indianapolis", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}}, "latestStatusDetail": {"code": "HL", "derivedCode": "HL", "statusByLocale": "Ready for pickup", "description": "Ready for pickup", "scanLocation": {"city": "GREENWOOD", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}, "ancillaryDetails": [{"reason": "015A", "reasonDescription": "Package available for pickup at FedEx Office: 331 S STATE RD 135", "action": "", "actionDescription": ""}]}, "dateAndTimes": [{"type": "ACTUAL_PICKUP", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "SHIP", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "ACTUAL_TENDER", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "ANTICIPATED_TENDER", "dateTime": "2023-05-15T00:00:00-06:00"}], "availableImages": [], "specialHandlings": [{"type": "DIRECT_SIGNATURE_REQUIRED", "description": "Direct Signature Required", "paymentType": "OTHER"}, {"type": "HOLD_AT_LOCATION", "description": "Hold at Location", "paymentType": "OTHER"}], "packageDetails": {"packagingDescription": {"type": "YOUR_PACKAGING", "description": "Package"}, "physicalPackagingType": "PACKAGE", "sequenceNumber": "1", "count": "1", "weightAndDimensions": {"weight": [{"value": "47.0", "unit": "LB"}, {"value": "21.32", "unit": "KG"}], "dimensions": [{"length": 48, "width": 30, "height": 5, "units": "IN"}, {"length": 121, "width": 76, "height": 12, "units": "CM"}]}, "packageContent": []}, "shipmentDetails": {"possessionStatus": true}, "scanEvents": [{"date": "2023-05-19T19:03:00-04:00", "eventType": "HP", "eventDescription": "Ready for recipient pickup", "exceptionCode": "015A", "exceptionDescription": "Package available for pickup at FedEx Office: 331 S STATE RD 135", "scanLocation": {"streetLines": ["331 S STATE RD 135 "], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46142", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "HNBKN", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T08:25:00-04:00", "eventType": "OD", "eventDescription": "On FedEx vehicle for delivery", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T07:31:24-04:00", "eventType": "HA", "eventDescription": "Hold at location request accepted", "exceptionCode": "A13", "exceptionDescription": "Shipment is being redirected as requested to FedEx Office", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T07:31:00-04:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T05:11:00-04:00", "eventType": "AR", "eventDescription": "At local FedEx facility", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T15:50:00-04:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0474", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T04:21:19-07:00", "eventType": "DP", "eventDescription": "Departed FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T02:57:54-05:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "UTICA", "stateOrProvinceCode": "MO", "postalCode": "64686", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T17:03:23-04:00", "eventType": "RR", "eventDescription": "Delivery option requested", "exceptionCode": "A12", "exceptionDescription": "Hold at FedEx Office request received - Check back later for shipment status", "scanLocation": {"streetLines": [""], "postalCode": "46142", "residential": false, "countryName": "United States"}, "locationId": "HNBKN", "locationType": "ENROUTE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T13:48:44-06:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "LARAMIE", "stateOrProvinceCode": "WY", "postalCode": "82070", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T01:47:24-06:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "KING HILL", "stateOrProvinceCode": "ID", "postalCode": "83633", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-16T12:47:07-07:00", "eventType": "DP", "eventDescription": "Departed FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T21:47:26-07:00", "eventType": "AO", "eventDescription": "Shipment arriving On-Time", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T21:46:00-07:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T17:15:00-07:00", "eventType": "PU", "eventDescription": "Picked up", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0971", "locationType": "PICKUP_LOCATION", "derivedStatusCode": "PU", "derivedStatus": "Picked up"}, {"date": "2023-05-15T13:29:00-07:00", "eventType": "OC", "eventDescription": "Shipment information sent to FedEx", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "postalCode": "98682", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "CUSTOMER", "derivedStatusCode": "IN", "derivedStatus": "Initiated"}], "availableNotifications": ["ON_DELIVERY", "ON_EXCEPTION", "ON_ESTIMATED_DELIVERY"], "deliveryDetails": {"deliveryAttempts": "0", "deliveryOptionEligibilityDetails": [{"option": "INDIRECT_SIGNATURE_RELEASE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "REDIRECT_TO_HOLD_AT_LOCATION", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "REROUTE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "RESCHEDULE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "RETURN_TO_SHIPPER", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "DISPUTE_DELIVERY", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "SUPPLEMENT_ADDRESS", "eligibility": "INELIGIBLE"}], "destinationServiceArea": "HELDPACKAGEAVAILABLEFORRECIPIENTPICKUPWITHADDRESS_HTML"}, "originLocation": {"locationContactAndAddress": {"address": {"city": "TROUTDALE", "stateOrProvinceCode": "OR", "countryCode": "US", "residential": false, "countryName": "United States"}}}, "holdAtLocation": {"locationContactAndAddress": {"address": {"streetLines": ["331 S STATE RD 135"], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46142", "countryCode": "US", "residential": false, "countryName": "United States"}}, "locationId": "HNBKN"}, "lastUpdatedDestinationAddress": {"city": "GREENWOOD", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}, "serviceCommitMessage": {"message": "Shipment is available for pickup at FedEx Office: 331 S STATE RD 135. We'll hold the shipment for five business days starting from May 19, 2023.", "type": "HELD_PACKAGE_AVAILABLE_FOR_RECIPIENT_PICKUP_WITH_ADDRESS"}, "serviceDetail": {"type": "FEDEX_GROUND", "description": "FedEx Ground", "shortDescription": "FG"}, "standardTransitTimeWindow": {"window": {"ends": "2023-05-19T00:00:00-06:00"}}, "estimatedDeliveryTimeWindow": {"window": {}}, "customDeliveryOptions": [{"type": "REDIRECT_TO_HOLD_AT_LOCATION", "status": "HELD"}], "goodsClassificationCode": "", "returnDetail": {}}]}]}}}	Ready for pickup	GREENWOOD, United States	N/A	2026-04-28 06:18:38.014599+02
3	772254547023	{"tracking_number": "772254547023", "status": "Ready for pickup", "current_location": "GREENWOOD, United States", "estimated_delivery": "N/A", "events": [{"at": "2023-05-19T19:03:00-04:00", "description": "Ready for recipient pickup", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T08:25:00-04:00", "description": "On FedEx vehicle for delivery", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T07:31:24-04:00", "description": "Hold at location request accepted", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T07:31:00-04:00", "description": "Arrived at FedEx location", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T05:11:00-04:00", "description": "At local FedEx facility", "location": "GREENWOOD, United States"}, {"at": "2023-05-18T15:50:00-04:00", "description": "Arrived at FedEx location", "location": "GREENWOOD, United States"}, {"at": "2023-05-18T04:21:19-07:00", "description": "Departed FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-18T02:57:54-05:00", "description": "In transit", "location": "UTICA, United States"}, {"at": "2023-05-17T17:03:23-04:00", "description": "Delivery option requested", "location": "United States"}, {"at": "2023-05-17T13:48:44-06:00", "description": "In transit", "location": "LARAMIE, United States"}, {"at": "2023-05-17T01:47:24-06:00", "description": "In transit", "location": "KING HILL, United States"}, {"at": "2023-05-16T12:47:07-07:00", "description": "Departed FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T21:47:26-07:00", "description": "Shipment arriving On-Time", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T21:46:00-07:00", "description": "Arrived at FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T17:15:00-07:00", "description": "Picked up", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T13:29:00-07:00", "description": "Shipment information sent to FedEx", "location": "United States"}], "source": "fedex_api", "raw": {"transactionId": "APIF_SV_TRKC_TxIDAPIF_SV_TxID18a9b1a3-6749-4e81-b985-fd49ba83c00f", "customertransactionId": "APIF_SV_TRKC_TxIDcustomer test", "output": {"alerts": [{"code": "VIRTUAL.RESPONSE", "message": "This is a Virtual Response."}], "completeTrackResults": [{"trackingNumber": "772254547023", "trackResults": [{"trackingNumberInfo": {"trackingNumber": "772254547023", "trackingNumberUniqueId": "12025~772254547023~FDEG", "carrierCode": "FDXG"}, "additionalTrackingInfo": {"nickname": "", "packageIdentifiers": [{"type": "PURCHASE_ORDER", "values": ["1683571649"], "trackingNumberUniqueId": "", "carrierCode": ""}, {"type": "INVOICE", "values": ["30186971"], "trackingNumberUniqueId": "", "carrierCode": ""}], "hasAssociatedShipments": false}, "shipperInformation": {"contact": {}, "address": {"city": "Vancouver", "stateOrProvinceCode": "WA", "countryCode": "US", "residential": false, "countryName": "United States"}}, "recipientInformation": {"contact": {}, "address": {"city": "Indianapolis", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}}, "latestStatusDetail": {"code": "HL", "derivedCode": "HL", "statusByLocale": "Ready for pickup", "description": "Ready for pickup", "scanLocation": {"city": "GREENWOOD", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}, "ancillaryDetails": [{"reason": "015A", "reasonDescription": "Package available for pickup at FedEx Office: 331 S STATE RD 135", "action": "", "actionDescription": ""}]}, "dateAndTimes": [{"type": "ACTUAL_PICKUP", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "SHIP", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "ACTUAL_TENDER", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "ANTICIPATED_TENDER", "dateTime": "2023-05-15T00:00:00-06:00"}], "availableImages": [], "specialHandlings": [{"type": "DIRECT_SIGNATURE_REQUIRED", "description": "Direct Signature Required", "paymentType": "OTHER"}, {"type": "HOLD_AT_LOCATION", "description": "Hold at Location", "paymentType": "OTHER"}], "packageDetails": {"packagingDescription": {"type": "YOUR_PACKAGING", "description": "Package"}, "physicalPackagingType": "PACKAGE", "sequenceNumber": "1", "count": "1", "weightAndDimensions": {"weight": [{"value": "47.0", "unit": "LB"}, {"value": "21.32", "unit": "KG"}], "dimensions": [{"length": 48, "width": 30, "height": 5, "units": "IN"}, {"length": 121, "width": 76, "height": 12, "units": "CM"}]}, "packageContent": []}, "shipmentDetails": {"possessionStatus": true}, "scanEvents": [{"date": "2023-05-19T19:03:00-04:00", "eventType": "HP", "eventDescription": "Ready for recipient pickup", "exceptionCode": "015A", "exceptionDescription": "Package available for pickup at FedEx Office: 331 S STATE RD 135", "scanLocation": {"streetLines": ["331 S STATE RD 135 "], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46142", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "HNBKN", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T08:25:00-04:00", "eventType": "OD", "eventDescription": "On FedEx vehicle for delivery", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T07:31:24-04:00", "eventType": "HA", "eventDescription": "Hold at location request accepted", "exceptionCode": "A13", "exceptionDescription": "Shipment is being redirected as requested to FedEx Office", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T07:31:00-04:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T05:11:00-04:00", "eventType": "AR", "eventDescription": "At local FedEx facility", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T15:50:00-04:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0474", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T04:21:19-07:00", "eventType": "DP", "eventDescription": "Departed FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T02:57:54-05:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "UTICA", "stateOrProvinceCode": "MO", "postalCode": "64686", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T17:03:23-04:00", "eventType": "RR", "eventDescription": "Delivery option requested", "exceptionCode": "A12", "exceptionDescription": "Hold at FedEx Office request received - Check back later for shipment status", "scanLocation": {"streetLines": [""], "postalCode": "46142", "residential": false, "countryName": "United States"}, "locationId": "HNBKN", "locationType": "ENROUTE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T13:48:44-06:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "LARAMIE", "stateOrProvinceCode": "WY", "postalCode": "82070", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T01:47:24-06:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "KING HILL", "stateOrProvinceCode": "ID", "postalCode": "83633", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-16T12:47:07-07:00", "eventType": "DP", "eventDescription": "Departed FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T21:47:26-07:00", "eventType": "AO", "eventDescription": "Shipment arriving On-Time", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T21:46:00-07:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T17:15:00-07:00", "eventType": "PU", "eventDescription": "Picked up", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0971", "locationType": "PICKUP_LOCATION", "derivedStatusCode": "PU", "derivedStatus": "Picked up"}, {"date": "2023-05-15T13:29:00-07:00", "eventType": "OC", "eventDescription": "Shipment information sent to FedEx", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "postalCode": "98682", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "CUSTOMER", "derivedStatusCode": "IN", "derivedStatus": "Initiated"}], "availableNotifications": ["ON_DELIVERY", "ON_EXCEPTION", "ON_ESTIMATED_DELIVERY"], "deliveryDetails": {"deliveryAttempts": "0", "deliveryOptionEligibilityDetails": [{"option": "INDIRECT_SIGNATURE_RELEASE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "REDIRECT_TO_HOLD_AT_LOCATION", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "REROUTE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "RESCHEDULE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "RETURN_TO_SHIPPER", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "DISPUTE_DELIVERY", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "SUPPLEMENT_ADDRESS", "eligibility": "INELIGIBLE"}], "destinationServiceArea": "HELDPACKAGEAVAILABLEFORRECIPIENTPICKUPWITHADDRESS_HTML"}, "originLocation": {"locationContactAndAddress": {"address": {"city": "TROUTDALE", "stateOrProvinceCode": "OR", "countryCode": "US", "residential": false, "countryName": "United States"}}}, "holdAtLocation": {"locationContactAndAddress": {"address": {"streetLines": ["331 S STATE RD 135"], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46142", "countryCode": "US", "residential": false, "countryName": "United States"}}, "locationId": "HNBKN"}, "lastUpdatedDestinationAddress": {"city": "GREENWOOD", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}, "serviceCommitMessage": {"message": "Shipment is available for pickup at FedEx Office: 331 S STATE RD 135. We'll hold the shipment for five business days starting from May 19, 2023.", "type": "HELD_PACKAGE_AVAILABLE_FOR_RECIPIENT_PICKUP_WITH_ADDRESS"}, "serviceDetail": {"type": "FEDEX_GROUND", "description": "FedEx Ground", "shortDescription": "FG"}, "standardTransitTimeWindow": {"window": {"ends": "2023-05-19T00:00:00-06:00"}}, "estimatedDeliveryTimeWindow": {"window": {}}, "customDeliveryOptions": [{"type": "REDIRECT_TO_HOLD_AT_LOCATION", "status": "HELD"}], "goodsClassificationCode": "", "returnDetail": {}}]}]}}}	Ready for pickup	GREENWOOD, United States	N/A	2026-04-28 06:21:28.479697+02
4	397773675776	{"tracking_number": "397773675776", "status": "Delivered", "current_location": "BRONX, United States", "estimated_delivery": "2023-05-04T16:42:00-04:00", "events": [{"at": "2023-05-04T16:42:00-04:00", "description": "Delivered", "location": "BRONX, United States"}, {"at": "2023-05-04T09:04:00-04:00", "description": "On FedEx vehicle for delivery", "location": "BRONX, United States"}, {"at": "2023-05-04T08:34:00-04:00", "description": "At local FedEx facility", "location": "BRONX, United States"}, {"at": "2023-05-04T04:23:00-04:00", "description": "Shipment arriving early", "location": "NEWARK, United States"}, {"at": "2023-05-04T04:22:00-04:00", "description": "Departed FedEx hub", "location": "NEWARK, United States"}, {"at": "2023-05-03T22:50:00-04:00", "description": "Arrived at FedEx hub", "location": "NEWARK, United States"}, {"at": "2023-05-03T19:28:00-05:00", "description": "Departed FedEx hub", "location": "MEMPHIS, United States"}, {"at": "2023-05-03T09:34:00-05:00", "description": "Shipment arriving On-Time", "location": "MEMPHIS, United States"}, {"at": "2023-05-03T09:33:00-05:00", "description": "Arrived at FedEx hub", "location": "MEMPHIS, United States"}, {"at": "2023-05-02T23:35:00-04:00", "description": "At local FedEx facility", "location": "TAMPA, United States"}, {"at": "2023-05-02T12:50:22-05:00", "description": "Shipment information sent to FedEx", "location": ""}, {"at": "2023-05-02T13:05:00-04:00", "description": "Picked up", "location": "PINELLAS PARK, United States"}], "source": "fedex_api", "raw": {"transactionId": "APIF_SV_TRKC_TxIDd2301b2f-1118-46e9-b478-af18cd465bc7", "customertransactionId": "APIF_SV_TRKC_TxIDcustomer test", "output": {"alerts": [{"code": "VIRTUAL.RESPONSE", "message": "This is a Virtual Response."}], "completeTrackResults": [{"trackingNumber": "397773675776", "trackResults": [{"trackingNumberInfo": {"trackingNumber": "397773675776", "trackingNumberUniqueId": "2460067000~397773675776~FX", "carrierCode": "FDXE"}, "additionalTrackingInfo": {"nickname": "", "packageIdentifiers": [{"type": "SHIPPER_REFERENCE", "values": ["Muchas Gracias por su Orden"], "trackingNumberUniqueId": "", "carrierCode": ""}], "hasAssociatedShipments": false}, "shipperInformation": {"contact": {}, "address": {"city": "Largo", "stateOrProvinceCode": "FL", "countryCode": "US", "residential": false, "countryName": "United States"}}, "recipientInformation": {"contact": {}, "address": {"city": "BRONX", "stateOrProvinceCode": "NY", "countryCode": "US", "residential": false, "countryName": "United States"}}, "latestStatusDetail": {"code": "DL", "derivedCode": "DL", "statusByLocale": "Delivered", "description": "Delivered", "scanLocation": {"city": "BRONX", "stateOrProvinceCode": "NY", "countryCode": "US", "residential": false, "countryName": "United States"}}, "dateAndTimes": [{"type": "ACTUAL_DELIVERY", "dateTime": "2023-05-04T16:42:00-04:00"}, {"type": "ACTUAL_PICKUP", "dateTime": "2023-05-02T13:05:00-04:00"}, {"type": "SHIP", "dateTime": "2023-05-02T00:00:00-06:00"}, {"type": "ACTUAL_TENDER", "dateTime": "2023-05-02T14:56:00-04:00"}], "availableImages": [{"type": "SIGNATURE_PROOF_OF_DELIVERY"}], "specialHandlings": [{"type": "DELIVER_WEEKDAY", "description": "Deliver Weekday", "paymentType": "OTHER"}, {"type": "RESIDENTIAL_DELIVERY", "description": "Residential Delivery", "paymentType": "OTHER"}], "packageDetails": {"packagingDescription": {"type": "FEDEX_PAK", "description": "FedEx Pak"}, "sequenceNumber": "1", "count": "1", "weightAndDimensions": {"weight": [{"value": "4.0", "unit": "LB"}, {"value": "1.81", "unit": "KG"}]}, "packageContent": []}, "shipmentDetails": {"possessionStatus": true, "weight": [{"value": "4.0", "unit": "LB"}, {"value": "1.81", "unit": "KG"}]}, "scanEvents": [{"date": "2023-05-04T16:42:00-04:00", "eventType": "DL", "eventDescription": "Delivered", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "BRONX", "stateOrProvinceCode": "NY", "postalCode": "10474", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "JREA", "locationType": "DELIVERY_LOCATION", "derivedStatusCode": "DL", "derivedStatus": "Delivered"}, {"date": "2023-05-04T09:04:00-04:00", "eventType": "OD", "eventDescription": "On FedEx vehicle for delivery", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "BRONX", "stateOrProvinceCode": "NY", "postalCode": "10454", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "JREA", "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-04T08:34:00-04:00", "eventType": "AR", "eventDescription": "At local FedEx facility", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "BRONX", "stateOrProvinceCode": "NY", "postalCode": "10454", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "JREA", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-04T04:23:00-04:00", "eventType": "AE", "eventDescription": "Shipment arriving early", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "NEWARK", "stateOrProvinceCode": "NJ", "postalCode": "07114", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "EWRHA", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-04T04:22:00-04:00", "eventType": "DP", "eventDescription": "Departed FedEx hub", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "NEWARK", "stateOrProvinceCode": "NJ", "postalCode": "07114", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "EWRHA", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-03T22:50:00-04:00", "eventType": "AR", "eventDescription": "Arrived at FedEx hub", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "NEWARK", "stateOrProvinceCode": "NJ", "postalCode": "07114", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "EWRRA", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-03T19:28:00-05:00", "eventType": "DP", "eventDescription": "Departed FedEx hub", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "MEMPHIS", "stateOrProvinceCode": "TN", "postalCode": "38118", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "MEMH", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-03T09:34:00-05:00", "eventType": "AO", "eventDescription": "Shipment arriving On-Time", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "MEMPHIS", "stateOrProvinceCode": "TN", "postalCode": "38118", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "MEMH", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-03T09:33:00-05:00", "eventType": "AR", "eventDescription": "Arrived at FedEx hub", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "MEMPHIS", "stateOrProvinceCode": "TN", "postalCode": "38118", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "MEMH", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-02T23:35:00-04:00", "eventType": "AF", "eventDescription": "At local FedEx facility", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TAMPA", "stateOrProvinceCode": "FL", "postalCode": "33614", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "TPAR", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-02T12:50:22-05:00", "eventType": "OC", "eventDescription": "Shipment information sent to FedEx", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "residential": false}, "locationType": "CUSTOMER", "derivedStatusCode": "IN", "derivedStatus": "Initiated"}, {"date": "2023-05-02T13:05:00-04:00", "eventType": "PU", "eventDescription": "Picked up", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "PINELLAS PARK", "stateOrProvinceCode": "FL", "postalCode": "33782", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "PIEA", "locationType": "PICKUP_LOCATION", "derivedStatusCode": "PU", "derivedStatus": "Picked up"}], "availableNotifications": ["ON_DELIVERY"], "deliveryDetails": {"actualDeliveryAddress": {"city": "BRONX", "stateOrProvinceCode": "NY", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "RESIDENCE", "locationDescription": "Residence", "deliveryAttempts": "0", "receivedByName": "M.OLMO", "deliveryOptionEligibilityDetails": [{"option": "INDIRECT_SIGNATURE_RELEASE", "eligibility": "INELIGIBLE"}, {"option": "REDIRECT_TO_HOLD_AT_LOCATION", "eligibility": "INELIGIBLE"}, {"option": "REROUTE", "eligibility": "INELIGIBLE"}, {"option": "RESCHEDULE", "eligibility": "INELIGIBLE"}, {"option": "RETURN_TO_SHIPPER", "eligibility": "INELIGIBLE"}, {"option": "DISPUTE_DELIVERY", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "SUPPLEMENT_ADDRESS", "eligibility": "INELIGIBLE"}]}, "originLocation": {"locationContactAndAddress": {"address": {"city": "PINELLAS PARK", "stateOrProvinceCode": "FL", "countryCode": "US", "residential": false, "countryName": "United States"}}, "locationId": "PIEA"}, "destinationLocation": {"locationContactAndAddress": {"address": {"city": "BRONX", "stateOrProvinceCode": "NY", "countryCode": "US", "residential": false, "countryName": "United States"}}, "locationType": ""}, "lastUpdatedDestinationAddress": {"city": "BRONX", "stateOrProvinceCode": "NY", "countryCode": "US", "residential": false, "countryName": "United States"}, "serviceDetail": {"type": "FEDEX_EXPRESS_SAVER", "description": "FedEx Express Saver", "shortDescription": "XS"}, "standardTransitTimeWindow": {"window": {"ends": "2023-05-05T20:00:00-04:00"}}, "estimatedDeliveryTimeWindow": {"window": {}}, "goodsClassificationCode": "", "returnDetail": {}}]}]}}}	Delivered	BRONX, United States	2023-05-04T16:42:00-04:00	2026-04-28 06:29:34.327735+02
5	123456789012	{"tracking_number": "123456789012", "status": "Ready for pickup", "current_location": "GREENWOOD, United States", "estimated_delivery": "N/A", "events": [{"at": "2023-05-19T19:03:00-04:00", "description": "Ready for recipient pickup", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T08:25:00-04:00", "description": "On FedEx vehicle for delivery", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T07:31:24-04:00", "description": "Hold at location request accepted", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T07:31:00-04:00", "description": "Arrived at FedEx location", "location": "GREENWOOD, United States"}, {"at": "2023-05-19T05:11:00-04:00", "description": "At local FedEx facility", "location": "GREENWOOD, United States"}, {"at": "2023-05-18T15:50:00-04:00", "description": "Arrived at FedEx location", "location": "GREENWOOD, United States"}, {"at": "2023-05-18T04:21:19-07:00", "description": "Departed FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-18T02:57:54-05:00", "description": "In transit", "location": "UTICA, United States"}, {"at": "2023-05-17T17:03:23-04:00", "description": "Delivery option requested", "location": "United States"}, {"at": "2023-05-17T13:48:44-06:00", "description": "In transit", "location": "LARAMIE, United States"}, {"at": "2023-05-17T01:47:24-06:00", "description": "In transit", "location": "KING HILL, United States"}, {"at": "2023-05-16T12:47:07-07:00", "description": "Departed FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T21:47:26-07:00", "description": "Shipment arriving On-Time", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T21:46:00-07:00", "description": "Arrived at FedEx location", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T17:15:00-07:00", "description": "Picked up", "location": "TROUTDALE, United States"}, {"at": "2023-05-15T13:29:00-07:00", "description": "Shipment information sent to FedEx", "location": "United States"}], "source": "fedex_api", "raw": {"transactionId": "APIF_SV_TRKC_TxIDAPIF_SV_TxID18a9b1a3-6749-4e81-b985-fd49ba83c00f", "customertransactionId": "APIF_SV_TRKC_TxIDcustomer test", "output": {"alerts": [{"code": "VIRTUAL.RESPONSE", "message": "This is a Virtual Response."}], "completeTrackResults": [{"trackingNumber": "123456789012", "trackResults": [{"trackingNumberInfo": {"trackingNumber": "123456789012", "trackingNumberUniqueId": "12025~123456789012~FDEG", "carrierCode": "FDXG"}, "additionalTrackingInfo": {"nickname": "", "packageIdentifiers": [{"type": "PURCHASE_ORDER", "values": ["1683571649"], "trackingNumberUniqueId": "", "carrierCode": ""}, {"type": "INVOICE", "values": ["30186971"], "trackingNumberUniqueId": "", "carrierCode": ""}], "hasAssociatedShipments": false}, "shipperInformation": {"contact": {}, "address": {"city": "Vancouver", "stateOrProvinceCode": "WA", "countryCode": "US", "residential": false, "countryName": "United States"}}, "recipientInformation": {"contact": {}, "address": {"city": "Indianapolis", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}}, "latestStatusDetail": {"code": "HL", "derivedCode": "HL", "statusByLocale": "Ready for pickup", "description": "Ready for pickup", "scanLocation": {"city": "GREENWOOD", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}, "ancillaryDetails": [{"reason": "015A", "reasonDescription": "Package available for pickup at FedEx Office: 331 S STATE RD 135", "action": "", "actionDescription": ""}]}, "dateAndTimes": [{"type": "ACTUAL_PICKUP", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "SHIP", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "ACTUAL_TENDER", "dateTime": "2023-05-15T00:00:00-06:00"}, {"type": "ANTICIPATED_TENDER", "dateTime": "2023-05-15T00:00:00-06:00"}], "availableImages": [], "specialHandlings": [{"type": "DIRECT_SIGNATURE_REQUIRED", "description": "Direct Signature Required", "paymentType": "OTHER"}, {"type": "HOLD_AT_LOCATION", "description": "Hold at Location", "paymentType": "OTHER"}], "packageDetails": {"packagingDescription": {"type": "YOUR_PACKAGING", "description": "Package"}, "physicalPackagingType": "PACKAGE", "sequenceNumber": "1", "count": "1", "weightAndDimensions": {"weight": [{"value": "47.0", "unit": "LB"}, {"value": "21.32", "unit": "KG"}], "dimensions": [{"length": 48, "width": 30, "height": 5, "units": "IN"}, {"length": 121, "width": 76, "height": 12, "units": "CM"}]}, "packageContent": []}, "shipmentDetails": {"possessionStatus": true}, "scanEvents": [{"date": "2023-05-19T19:03:00-04:00", "eventType": "HP", "eventDescription": "Ready for recipient pickup", "exceptionCode": "015A", "exceptionDescription": "Package available for pickup at FedEx Office: 331 S STATE RD 135", "scanLocation": {"streetLines": ["331 S STATE RD 135 "], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46142", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "HNBKN", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T08:25:00-04:00", "eventType": "OD", "eventDescription": "On FedEx vehicle for delivery", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T07:31:24-04:00", "eventType": "HA", "eventDescription": "Hold at location request accepted", "exceptionCode": "A13", "exceptionDescription": "Shipment is being redirected as requested to FedEx Office", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T07:31:00-04:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-19T05:11:00-04:00", "eventType": "AR", "eventDescription": "At local FedEx facility", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0472", "locationType": "DESTINATION_FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T15:50:00-04:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46143", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0474", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T04:21:19-07:00", "eventType": "DP", "eventDescription": "Departed FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-18T02:57:54-05:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "UTICA", "stateOrProvinceCode": "MO", "postalCode": "64686", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T17:03:23-04:00", "eventType": "RR", "eventDescription": "Delivery option requested", "exceptionCode": "A12", "exceptionDescription": "Hold at FedEx Office request received - Check back later for shipment status", "scanLocation": {"streetLines": [""], "postalCode": "46142", "residential": false, "countryName": "United States"}, "locationId": "HNBKN", "locationType": "ENROUTE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T13:48:44-06:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "LARAMIE", "stateOrProvinceCode": "WY", "postalCode": "82070", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-17T01:47:24-06:00", "eventType": "IT", "eventDescription": "In transit", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "KING HILL", "stateOrProvinceCode": "ID", "postalCode": "83633", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "VEHICLE", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-16T12:47:07-07:00", "eventType": "DP", "eventDescription": "Departed FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T21:47:26-07:00", "eventType": "AO", "eventDescription": "Shipment arriving On-Time", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T21:46:00-07:00", "eventType": "AR", "eventDescription": "Arrived at FedEx location", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0972", "locationType": "FEDEX_FACILITY", "derivedStatusCode": "IT", "derivedStatus": "In transit"}, {"date": "2023-05-15T17:15:00-07:00", "eventType": "PU", "eventDescription": "Picked up", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "city": "TROUTDALE", "stateOrProvinceCode": "OR", "postalCode": "97060", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationId": "0971", "locationType": "PICKUP_LOCATION", "derivedStatusCode": "PU", "derivedStatus": "Picked up"}, {"date": "2023-05-15T13:29:00-07:00", "eventType": "OC", "eventDescription": "Shipment information sent to FedEx", "exceptionCode": "", "exceptionDescription": "", "scanLocation": {"streetLines": [""], "postalCode": "98682", "countryCode": "US", "residential": false, "countryName": "United States"}, "locationType": "CUSTOMER", "derivedStatusCode": "IN", "derivedStatus": "Initiated"}], "availableNotifications": ["ON_DELIVERY", "ON_EXCEPTION", "ON_ESTIMATED_DELIVERY"], "deliveryDetails": {"deliveryAttempts": "0", "deliveryOptionEligibilityDetails": [{"option": "INDIRECT_SIGNATURE_RELEASE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "REDIRECT_TO_HOLD_AT_LOCATION", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "REROUTE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "RESCHEDULE", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "RETURN_TO_SHIPPER", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "DISPUTE_DELIVERY", "eligibility": "POSSIBLY_ELIGIBLE"}, {"option": "SUPPLEMENT_ADDRESS", "eligibility": "INELIGIBLE"}], "destinationServiceArea": "HELDPACKAGEAVAILABLEFORRECIPIENTPICKUPWITHADDRESS_HTML"}, "originLocation": {"locationContactAndAddress": {"address": {"city": "TROUTDALE", "stateOrProvinceCode": "OR", "countryCode": "US", "residential": false, "countryName": "United States"}}}, "holdAtLocation": {"locationContactAndAddress": {"address": {"streetLines": ["331 S STATE RD 135"], "city": "GREENWOOD", "stateOrProvinceCode": "IN", "postalCode": "46142", "countryCode": "US", "residential": false, "countryName": "United States"}}, "locationId": "HNBKN"}, "lastUpdatedDestinationAddress": {"city": "GREENWOOD", "stateOrProvinceCode": "IN", "countryCode": "US", "residential": false, "countryName": "United States"}, "serviceCommitMessage": {"message": "Shipment is available for pickup at FedEx Office: 331 S STATE RD 135. We'll hold the shipment for five business days starting from May 19, 2023.", "type": "HELD_PACKAGE_AVAILABLE_FOR_RECIPIENT_PICKUP_WITH_ADDRESS"}, "serviceDetail": {"type": "FEDEX_GROUND", "description": "FedEx Ground", "shortDescription": "FG"}, "standardTransitTimeWindow": {"window": {"ends": "2023-05-19T00:00:00-06:00"}}, "estimatedDeliveryTimeWindow": {"window": {}}, "customDeliveryOptions": [{"type": "REDIRECT_TO_HOLD_AT_LOCATION", "status": "HELD"}], "goodsClassificationCode": "", "returnDetail": {}}]}]}}}	Ready for pickup	GREENWOOD, United States	N/A	2026-04-28 21:22:30.053998+02
\.


--
-- Data for Name: support_tickets; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.support_tickets (id, user_id, subject, message, status, admin_note, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: tracking_requests; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.tracking_requests (id, user_id, tracking_number, user_question, bot_response, status, current_location, estimated_delivery, created_at, session_id) FROM stdin;
1	1	1223874384713	ou est mon coulis 1223874384713	Voici le suivi pour le colis **1223874384713**.\n- Statut : En transit\n- Localisation : Hub Casablanca\n- Livraison estimée : 2026-04-25	En transit	Hub Casablanca	2026-04-25	2026-04-22 03:20:14.174462+02	\N
5	3	123456789012	Où est mon colis 123456789012 ?	Voici le suivi pour le colis **123456789012**.\n- Statut : Ready for pickup\n- Localisation : GREENWOOD, United States\n- Livraison estimée : N/A	Ready for pickup	GREENWOOD, United States	N/A	2026-04-28 21:22:30.053998+02	\N
6	4	123456789012	Où est mon colis 123456789012 ?	Voici le suivi pour le colis **123456789012**.\n- Statut : Ready for pickup\n- Localisation : GREENWOOD, United States\n- Livraison estimée : N/A	Ready for pickup	GREENWOOD, United States	N/A	2026-04-29 00:00:30.541708+02	\N
7	5	123456789012	Où est mon colis 123456789012 ?	Voici le suivi pour le colis **123456789012**.\n- Statut : Ready for pickup\n- Localisation : GREENWOOD, United States\n- Livraison estimée : N/A	Ready for pickup	GREENWOOD, United States	N/A	2026-05-26 20:35:20.074505+02	\N
8	10	123456789012	Où est mon colis 123456789012 ?	Voici le suivi pour le colis **123456789012**.\n- Statut : Ready for pickup\n- Localisation : GREENWOOD, United States\n- Livraison estimée : N/A	Ready for pickup	GREENWOOD, United States	N/A	2026-05-31 20:28:21.445304+02	\N
\.


--
-- Data for Name: user_sessions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_sessions (id, user_id, token_id, browser, machine, location, is_active, created_at, updated_at) FROM stdin;
3	3	6c8223daf2f741ac83d3c5d8303bd79c	Chrome	Windows	127.0.0.1	t	2026-04-28 19:48:44.662801+02	2026-04-28 19:48:44.662801+02
4	3	3d43440cf73c41fdbe59a95072075dad	Chrome	Windows	127.0.0.1	t	2026-04-28 20:34:06.58595+02	2026-04-28 20:34:06.58595+02
5	3	1a92a7beb3da486eaf7f6106668e0cea	Chrome	Windows	127.0.0.1	t	2026-04-28 21:22:13.853013+02	2026-04-28 21:22:13.853013+02
6	3	a7270dc3e1244c758a4b4dc5df621fe8	Chrome	Windows	127.0.0.1	t	2026-04-28 21:48:43.968867+02	2026-04-28 21:48:43.968867+02
7	4	6a223295368f42638d2aa67d5cd89107	Chrome	Windows	127.0.0.1	t	2026-04-28 21:49:34.298216+02	2026-04-28 21:49:34.298216+02
8	4	7ad3f8bcdcda4963b7a14bc852d2ee19	Chrome	Windows	127.0.0.1	t	2026-04-28 22:12:50.058338+02	2026-04-28 22:12:50.058338+02
9	3	1f0c34ba06974bcab8fa427662fc9df8	Chrome	Windows	127.0.0.1	t	2026-04-28 22:16:45.889762+02	2026-04-28 22:16:45.889762+02
10	4	a792e4022ad6471ca4976d308d107d10	Chrome	Windows	127.0.0.1	t	2026-04-28 22:17:37.490083+02	2026-04-28 22:17:37.490083+02
11	5	36cb65c0f79241a5b50d9f2b42b8a409	Edge	Windows	127.0.0.1	t	2026-05-26 20:00:31.374471+02	2026-05-26 20:00:31.374471+02
12	5	fde5c1dcfc7b44418c125055ebd0f3c3	Edge	Windows	127.0.0.1	t	2026-05-31 16:45:02.704236+02	2026-05-31 16:45:02.704236+02
13	5	cfa43894cd3d48b0be560d1da3c207ab	Edge	Windows	127.0.0.1	t	2026-05-31 17:27:00.937396+02	2026-05-31 17:27:00.937396+02
14	5	da72743fca0745479196ea574476236f	Edge	Windows	127.0.0.1	t	2026-05-31 17:27:17.476916+02	2026-05-31 17:27:17.476916+02
15	5	9159d3e077614d73a03e4ec6c17c17f2	Edge	Windows	127.0.0.1	t	2026-05-31 17:29:44.473556+02	2026-05-31 17:29:44.473556+02
16	7	3211ec24dc81479b8ea15f58473532b3	Edge	Windows	127.0.0.1	t	2026-05-31 17:33:11.902716+02	2026-05-31 17:33:11.902716+02
17	6	f5be382de9ee4378bbfc8226c2f3e677	Edge	Windows	127.0.0.1	t	2026-05-31 17:36:52.272071+02	2026-05-31 17:36:52.272071+02
18	6	c51fc78e783e4dbba933b5cfc309512c	Unknown	Windows	127.0.0.1	t	2026-05-31 18:11:30.116098+02	2026-05-31 18:11:30.116098+02
19	6	3b6a658476264ec19b4053a4e0b7c108	Unknown	Windows	127.0.0.1	t	2026-05-31 18:29:40.682598+02	2026-05-31 18:29:40.682598+02
21	6	df576e62fc6a41f8b3027aeacbfdb008	Edge	Windows	127.0.0.1	t	2026-05-31 18:37:04.89879+02	2026-05-31 18:37:04.89879+02
22	6	cd23197ab4664b71a156f984332cc7bd	Unknown	Windows	127.0.0.1	t	2026-05-31 19:25:23.345303+02	2026-05-31 19:25:23.345303+02
23	6	cffd6f4f1a6346809182e9fccc066905	Edge	Windows	127.0.0.1	t	2026-05-31 19:27:39.207239+02	2026-05-31 19:27:39.207239+02
24	6	856cc89536814d7694d79518f4ee2833	Unknown	Windows	127.0.0.1	t	2026-05-31 19:36:52.549234+02	2026-05-31 19:36:52.549234+02
25	11	f1751a0309864afd98dcb064dd24aee5	Unknown	Windows	127.0.0.1	t	2026-05-31 19:37:06.152769+02	2026-05-31 19:37:06.152769+02
26	6	44f4efce149a469ca6e8df009facf978	Unknown	Windows	127.0.0.1	t	2026-05-31 19:37:36.304225+02	2026-05-31 19:37:36.304225+02
27	10	1e56ce6dec15455e95b17edc54b032f8	Chrome	Windows	127.0.0.1	t	2026-05-31 19:38:45.488792+02	2026-05-31 19:38:45.488792+02
28	6	9ef0f9f06c9b47bc84ffe9517ac26e3e	Unknown	Windows	127.0.0.1	t	2026-05-31 19:45:33.924809+02	2026-05-31 19:45:33.924809+02
29	6	6b86a272b44842b283c9171616bcc4f1	Unknown	Windows	127.0.0.1	t	2026-05-31 19:48:17.968108+02	2026-05-31 19:48:17.968108+02
30	6	c68edccb810d4a279bd9ae3a6d59d3a8	Edge	Windows	127.0.0.1	t	2026-05-31 19:48:36.627427+02	2026-05-31 19:48:36.627427+02
31	10	c66ea2df97d14cc0ad65154fcd25a3f1	Edge	Windows	127.0.0.1	t	2026-05-31 19:51:17.449729+02	2026-05-31 19:51:17.449729+02
32	10	558c7d5d40a5482fbf7bd46862031989	Edge	Windows	127.0.0.1	t	2026-05-31 19:51:46.651046+02	2026-05-31 19:51:46.651046+02
33	6	96295224dbbc4905b011ef70a121f52c	Unknown	Windows	127.0.0.1	t	2026-05-31 20:07:03.845931+02	2026-05-31 20:07:03.845931+02
34	7	e0db2a0922d24e88b82cf10119514446	Unknown	Windows	127.0.0.1	t	2026-05-31 20:07:20.433177+02	2026-05-31 20:07:20.433177+02
35	10	e229d178b6604178812e492002c8ccc1	Edge	Windows	127.0.0.1	t	2026-05-31 20:14:51.576244+02	2026-05-31 20:14:51.576244+02
36	10	4bc80d24de664fb7a12ea81e64f3f0c4	Edge	Windows	127.0.0.1	t	2026-05-31 20:15:15.12133+02	2026-05-31 20:15:15.12133+02
37	10	de9415f6b1d84918abcf2d1e6fa77b74	Chrome	Windows	127.0.0.1	t	2026-05-31 20:16:26.770725+02	2026-05-31 20:16:26.770725+02
38	10	60d89181d1b24f6dbdb16fcc6495cb92	Edge	Windows	127.0.0.1	t	2026-06-01 16:44:19.843165+02	2026-06-01 16:44:19.843165+02
39	6	b6e289b4a7d54fd2b1b356df4741e9bd	Edge	Windows	127.0.0.1	t	2026-06-01 18:55:53.38631+02	2026-06-01 18:55:53.38631+02
40	10	f6812db5d8b94001a602372d4f0d6ffc	Edge	Windows	127.0.0.1	t	2026-06-01 19:30:38.938022+02	2026-06-01 19:30:38.938022+02
41	10	980a6a3e994b47acb4576910d054625c	Edge	Windows	127.0.0.1	t	2026-06-01 19:31:00.913305+02	2026-06-01 19:31:00.913305+02
42	6	431d01c3021242478bfe3065cc5f60bb	Edge	Windows	127.0.0.1	t	2026-06-01 19:31:28.737355+02	2026-06-01 19:31:28.737355+02
43	6	1616bed048c94305b7dfd4ae298fa4aa	Edge	Windows	127.0.0.1	t	2026-06-01 19:49:10.334101+02	2026-06-01 19:49:10.334101+02
44	6	d11024f7121642fa84d8fa7509041edb	Unknown	Unknown	127.0.0.1	t	2026-06-02 02:31:31.085362+02	2026-06-02 02:31:31.085362+02
45	6	24fa7deb1a174d489679dbc41756010a	Unknown	Unknown	127.0.0.1	t	2026-06-02 03:42:10.521533+02	2026-06-02 03:42:10.521533+02
46	6	f6dea80d3735414690014bf62f28c0a6	Edge	Windows	127.0.0.1	t	2026-06-02 05:20:36.265644+02	2026-06-02 05:20:36.265644+02
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, full_name, email, password_hash, role, preferred_language, created_at, organization_id, status, activation_token, activation_expires_at, qr_login_token_digest, response_preferences, quota_messages_per_day, quota_trackings_per_day, quota_exports_per_day, preference_profile_json) FROM stdin;
1	abdo	abdo@gmail.com	$2b$12$W3SNBO/gEdDvy8slEgRtjuOJcXhad0R4GhzRDJu/tjch.iUfoMFTm	client	fr	2026-04-22 03:14:46.814694+02	e5b971b0-340e-40dd-a64e-059413bdcc32	active	\N	\N	\N		\N	\N	\N	{}
3	abdo	abdo1234@gmail.com	$2b$12$y5hMx.Qaj8upRmaIHyP.vuiJnpiExhgqdmV5qIKDhMtI.nuh3cXEG	client	fr	2026-04-28 19:48:40.016433+02	79bd7c5d-9c2f-4949-aa35-8f103f6a9b34	active	\N	\N	\N		\N	\N	\N	{}
4	sak	sak@gmail.com	$2b$12$Oa8l5/IltK.fbHqxOnzMG.ZqjvjD4pEVDgSI3G/wv4dBkXE3w03Ue	client	fr	2026-04-28 21:49:27.702682+02	8ea1a3b5-6dfd-4ff9-89d6-b25acfb13f3c	active	\N	\N	\N		\N	\N	\N	{}
5	amine	amine@gmail.com	$2b$12$8iHZW3D013PkQoGyzouWgOvBhkauRuSXKXhadVS5/uXE9t1i42fT6	client	fr	2026-05-26 20:00:27.003728+02	14e3ebba-eb87-4405-be60-e259a66723ed	active	\N	\N	\N		\N	\N	\N	{}
9	Test Pending	sxr2123+pending@gmail.com	$2b$12$FtNV4S02ka5EnLq79BfjhuXzZ.8ZUpGk3wyepW8iRGg0R6hB/nQoG	employe	fr	2026-05-31 19:25:22.859837+02	053fdf8f-e081-4707-a59d-c4b9857d56fb	active	\N	\N	\N		\N	\N	\N	{}
11	Flow Test	sxr2123+flow@gmail.com	$2b$12$7sDf4MoGzOlV0sdhLKVur.YUsvXdkG2VEXx9wCF4NVbi.IE/cxkwa	employe	fr	2026-05-31 19:36:52.049104+02	7a8845b8-1478-498f-a51f-112a9574c7e4	active	\N	\N	\N		\N	\N	\N	{}
7	abdo	abdo1@gmail.com	$2b$12$vFQ4Uz07JedYKLASHXVRGObQ6zI2Wol5xjHOHW6r81u/8bK86Cmwi	employe	fr	2026-05-31 17:33:07.222306+02	f8849ae2-b36f-4d43-86dd-4cbee6c9936d	active	\N	\N	0e7d45c8befe7bda76cbeaf73b0b9e6ee7fe6c7108a4e267fa9940730241f36b		\N	\N	\N	{}
10	jessy	sxr2123@gmail.com	$2b$12$YCAGWVtKpnJ9LBkC/byNaOYa6Ulv6k7e5BXxk0waZib.kXlUUifTy	employe	fr	2026-05-31 19:26:55.62226+02	054953bd-774c-443d-aa1c-0be361831f24	active	\N	\N	a4ea3146e159da88c97b004aae8bd9783dec3b93a85780b7c2385f9efb3917af		\N	\N	\N	{}
6	Administrateur Globex	admin@globex.ma	$2b$12$QkYqHD42689mts8IBrpqZuW2tAWXZDEzqWaCl14ISb8/PJyMJxhBS	admin	en	2026-05-31 17:22:28.020043+02	c1076f32-246f-40b2-9ae2-7768f2d86cca	active	\N	\N	\N		\N	\N	\N	{}
12	noor	elhajbinourelhouda@gmail.com	$2b$12$uWVfAf4eDdqw6D7u/E9DduX4A.T.W7n38AkBcR6Ls5IsR76D9E4aG	employe	fr	2026-05-31 19:45:16.402999+02	0da97f3f-ea82-4b92-a549-db364eafb525	active	\N	\N	\N		10	10	10	{}
\.


--
-- Name: activity_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.activity_logs_id_seq', 31, true);


--
-- Name: chat_collections_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.chat_collections_id_seq', 4, true);


--
-- Name: chat_messages_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.chat_messages_id_seq', 92, true);


--
-- Name: chat_sessions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.chat_sessions_id_seq', 33, true);


--
-- Name: login_otp_challenges_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.login_otp_challenges_id_seq', 10, true);


--
-- Name: preference_submissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.preference_submissions_id_seq', 1, false);


--
-- Name: shared_conversation_links_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.shared_conversation_links_id_seq', 4, true);


--
-- Name: shipment_cache_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.shipment_cache_id_seq', 5, true);


--
-- Name: support_tickets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.support_tickets_id_seq', 1, false);


--
-- Name: tracking_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.tracking_requests_id_seq', 8, true);


--
-- Name: user_sessions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_sessions_id_seq', 46, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 12, true);


--
-- Name: activity_logs activity_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_pkey PRIMARY KEY (id);


--
-- Name: chat_collections chat_collections_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_collections
    ADD CONSTRAINT chat_collections_pkey PRIMARY KEY (id);


--
-- Name: chat_messages chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_pkey PRIMARY KEY (id);


--
-- Name: chat_sessions chat_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_pkey PRIMARY KEY (id);


--
-- Name: login_otp_challenges login_otp_challenges_challenge_token_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.login_otp_challenges
    ADD CONSTRAINT login_otp_challenges_challenge_token_key UNIQUE (challenge_token);


--
-- Name: login_otp_challenges login_otp_challenges_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.login_otp_challenges
    ADD CONSTRAINT login_otp_challenges_pkey PRIMARY KEY (id);


--
-- Name: preference_submissions preference_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.preference_submissions
    ADD CONSTRAINT preference_submissions_pkey PRIMARY KEY (id);


--
-- Name: shared_conversation_links shared_conversation_links_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shared_conversation_links
    ADD CONSTRAINT shared_conversation_links_pkey PRIMARY KEY (id);


--
-- Name: shipment_cache shipment_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment_cache
    ADD CONSTRAINT shipment_cache_pkey PRIMARY KEY (id);


--
-- Name: support_tickets support_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT support_tickets_pkey PRIMARY KEY (id);


--
-- Name: tracking_requests tracking_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tracking_requests
    ADD CONSTRAINT tracking_requests_pkey PRIMARY KEY (id);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_activity_logs_action; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_activity_logs_action ON public.activity_logs USING btree (action);


--
-- Name: ix_activity_logs_actor_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_activity_logs_actor_user_id ON public.activity_logs USING btree (actor_user_id);


--
-- Name: ix_activity_logs_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_activity_logs_category ON public.activity_logs USING btree (category);


--
-- Name: ix_activity_logs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_activity_logs_created_at ON public.activity_logs USING btree (created_at);


--
-- Name: ix_activity_logs_level; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_activity_logs_level ON public.activity_logs USING btree (level);


--
-- Name: ix_activity_logs_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_activity_logs_user_id ON public.activity_logs USING btree (user_id);


--
-- Name: ix_chat_collections_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_chat_collections_user_id ON public.chat_collections USING btree (user_id);


--
-- Name: ix_chat_messages_session_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_chat_messages_session_id ON public.chat_messages USING btree (session_id);


--
-- Name: ix_chat_sessions_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_chat_sessions_user_id ON public.chat_sessions USING btree (user_id);


--
-- Name: ix_login_otp_challenges_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_login_otp_challenges_user_id ON public.login_otp_challenges USING btree (user_id);


--
-- Name: ix_preference_submissions_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_preference_submissions_created_at ON public.preference_submissions USING btree (created_at);


--
-- Name: ix_preference_submissions_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_preference_submissions_status ON public.preference_submissions USING btree (status);


--
-- Name: ix_preference_submissions_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_preference_submissions_user_id ON public.preference_submissions USING btree (user_id);


--
-- Name: ix_preference_submissions_user_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_preference_submissions_user_status ON public.preference_submissions USING btree (user_id, status);


--
-- Name: ix_shared_conversation_links_owner_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_shared_conversation_links_owner_user_id ON public.shared_conversation_links USING btree (owner_user_id);


--
-- Name: ix_shared_conversation_links_session_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_shared_conversation_links_session_id ON public.shared_conversation_links USING btree (session_id);


--
-- Name: ix_shared_conversation_links_share_token; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_shared_conversation_links_share_token ON public.shared_conversation_links USING btree (share_token);


--
-- Name: ix_shipment_cache_tracking_number; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_shipment_cache_tracking_number ON public.shipment_cache USING btree (tracking_number);


--
-- Name: ix_support_tickets_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_support_tickets_status ON public.support_tickets USING btree (status, created_at DESC);


--
-- Name: ix_support_tickets_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_support_tickets_user_id ON public.support_tickets USING btree (user_id);


--
-- Name: ix_tracking_requests_session_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_tracking_requests_session_id ON public.tracking_requests USING btree (session_id);


--
-- Name: ix_tracking_requests_tracking_number; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_tracking_requests_tracking_number ON public.tracking_requests USING btree (tracking_number);


--
-- Name: ix_tracking_requests_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_tracking_requests_user_id ON public.tracking_requests USING btree (user_id);


--
-- Name: ix_user_sessions_token_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_user_sessions_token_id ON public.user_sessions USING btree (token_id);


--
-- Name: ix_user_sessions_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_user_sessions_user_id ON public.user_sessions USING btree (user_id);


--
-- Name: ix_users_activation_token; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_activation_token ON public.users USING btree (activation_token);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_organization_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_organization_id ON public.users USING btree (organization_id);


--
-- Name: ix_users_qr_login_token_digest; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_qr_login_token_digest ON public.users USING btree (qr_login_token_digest) WHERE (qr_login_token_digest IS NOT NULL);


--
-- Name: activity_logs activity_logs_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: activity_logs activity_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: chat_collections chat_collections_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_collections
    ADD CONSTRAINT chat_collections_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: chat_messages chat_messages_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(id) ON DELETE CASCADE;


--
-- Name: chat_sessions chat_sessions_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.chat_collections(id) ON DELETE SET NULL;


--
-- Name: chat_sessions chat_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: login_otp_challenges login_otp_challenges_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.login_otp_challenges
    ADD CONSTRAINT login_otp_challenges_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: preference_submissions preference_submissions_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.preference_submissions
    ADD CONSTRAINT preference_submissions_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: preference_submissions preference_submissions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.preference_submissions
    ADD CONSTRAINT preference_submissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: shared_conversation_links shared_conversation_links_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shared_conversation_links
    ADD CONSTRAINT shared_conversation_links_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: shared_conversation_links shared_conversation_links_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shared_conversation_links
    ADD CONSTRAINT shared_conversation_links_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(id) ON DELETE CASCADE;


--
-- Name: support_tickets support_tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT support_tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: tracking_requests tracking_requests_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tracking_requests
    ADD CONSTRAINT tracking_requests_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(id) ON DELETE SET NULL;


--
-- Name: tracking_requests tracking_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tracking_requests
    ADD CONSTRAINT tracking_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_sessions user_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

