-- PostgreSQL schema generated from SQLAlchemy models (app/models.py) + append-only audit trigger (app/db.py).
-- The application creates this automatically on startup; this file is for review and DBA use.


CREATE FUNCTION public.audit_log_block() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
       BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$;

CREATE TABLE public.approvals (
    id integer NOT NULL,
    report_id integer NOT NULL,
    user_id integer NOT NULL,
    decision character varying(32) NOT NULL,
    comment text NOT NULL,
    qualification character varying(255) NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.approvals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.approvals_id_seq OWNED BY public.approvals.id;

CREATE TABLE public.audit_log (
    id integer NOT NULL,
    ts timestamp with time zone NOT NULL,
    user_id integer,
    user_email character varying(255),
    action character varying(64) NOT NULL,
    entity character varying(64) NOT NULL,
    entity_id character varying(64) NOT NULL,
    detail json NOT NULL,
    prev_hash character varying(64) NOT NULL,
    hash character varying(64) NOT NULL
);

CREATE SEQUENCE public.audit_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.audit_log_id_seq OWNED BY public.audit_log.id;

CREATE TABLE public.corrective_actions (
    id integer NOT NULL,
    report_id integer,
    description text NOT NULL,
    action_type character varying(16) NOT NULL,
    responsible character varying(255) NOT NULL,
    due_date date,
    status character varying(16) NOT NULL,
    closure_note text NOT NULL,
    closed_by integer,
    closed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.corrective_actions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.corrective_actions_id_seq OWNED BY public.corrective_actions.id;

CREATE TABLE public.dg_entries (
    id integer NOT NULL,
    source_id integer NOT NULL,
    un_number character varying(8) NOT NULL,
    variant character varying(64) NOT NULL,
    proper_shipping_name character varying(512) NOT NULL,
    hazard_class character varying(8) NOT NULL,
    subsidiary_hazards json NOT NULL,
    packing_groups json NOT NULL,
    special_provisions json,
    marine_pollutant character varying(16),
    mode_data json NOT NULL,
    section_ref character varying(255) NOT NULL,
    synonyms json NOT NULL,
    cas_numbers json NOT NULL,
    verification_status character varying(32) NOT NULL,
    verified_by character varying(255),
    verified_at timestamp with time zone,
    verification_ref text,
    notes text NOT NULL
);

CREATE SEQUENCE public.dg_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.dg_entries_id_seq OWNED BY public.dg_entries.id;

CREATE TABLE public.regulatory_sources (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    rule_set character varying(16) NOT NULL,
    publisher character varying(255) NOT NULL,
    title character varying(512) NOT NULL,
    edition character varying(128) NOT NULL,
    amendment character varying(128) NOT NULL,
    publication_date date,
    effective_date date,
    expiry_date date,
    licence text NOT NULL,
    authorized_usage text NOT NULL,
    location character varying(1024) NOT NULL,
    ingestion_date timestamp with time zone NOT NULL,
    verification_status character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    content_loaded boolean NOT NULL,
    notes text NOT NULL
);

CREATE SEQUENCE public.regulatory_sources_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.regulatory_sources_id_seq OWNED BY public.regulatory_sources.id;

CREATE TABLE public.reports (
    id integer NOT NULL,
    kind character varying(48) NOT NULL,
    title character varying(512) NOT NULL,
    status character varying(32) NOT NULL,
    criticality character varying(16) NOT NULL,
    content json NOT NULL,
    inputs json NOT NULL,
    created_by integer,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.reports_id_seq OWNED BY public.reports.id;

CREATE TABLE public.risk_matrices (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    config json NOT NULL,
    is_default boolean NOT NULL
);

CREATE SEQUENCE public.risk_matrices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.risk_matrices_id_seq OWNED BY public.risk_matrices.id;

CREATE TABLE public.rule_tables (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    source_id integer NOT NULL,
    name character varying(255) NOT NULL,
    section_ref character varying(255) NOT NULL,
    data json NOT NULL,
    complete boolean NOT NULL,
    verification_status character varying(32) NOT NULL,
    verified_by character varying(255),
    verified_at timestamp with time zone,
    notes text NOT NULL
);

CREATE SEQUENCE public.rule_tables_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.rule_tables_id_seq OWNED BY public.rule_tables.id;

CREATE TABLE public.stored_files (
    id integer NOT NULL,
    sha256 character varying(64) NOT NULL,
    original_name character varying(255) NOT NULL,
    content_type character varying(128) NOT NULL,
    size integer NOT NULL,
    path character varying(1024) NOT NULL,
    purpose character varying(64) NOT NULL,
    uploaded_by integer,
    created_at timestamp with time zone NOT NULL,
    extraction json
);

CREATE SEQUENCE public.stored_files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.stored_files_id_seq OWNED BY public.stored_files.id;

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role character varying(32) NOT NULL,
    qualification character varying(255) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;

ALTER TABLE ONLY public.approvals ALTER COLUMN id SET DEFAULT nextval('public.approvals_id_seq'::regclass);

ALTER TABLE ONLY public.audit_log ALTER COLUMN id SET DEFAULT nextval('public.audit_log_id_seq'::regclass);

ALTER TABLE ONLY public.corrective_actions ALTER COLUMN id SET DEFAULT nextval('public.corrective_actions_id_seq'::regclass);

ALTER TABLE ONLY public.dg_entries ALTER COLUMN id SET DEFAULT nextval('public.dg_entries_id_seq'::regclass);

ALTER TABLE ONLY public.regulatory_sources ALTER COLUMN id SET DEFAULT nextval('public.regulatory_sources_id_seq'::regclass);

ALTER TABLE ONLY public.reports ALTER COLUMN id SET DEFAULT nextval('public.reports_id_seq'::regclass);

ALTER TABLE ONLY public.risk_matrices ALTER COLUMN id SET DEFAULT nextval('public.risk_matrices_id_seq'::regclass);

ALTER TABLE ONLY public.rule_tables ALTER COLUMN id SET DEFAULT nextval('public.rule_tables_id_seq'::regclass);

ALTER TABLE ONLY public.stored_files ALTER COLUMN id SET DEFAULT nextval('public.stored_files_id_seq'::regclass);

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_hash_key UNIQUE (hash);

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.corrective_actions
    ADD CONSTRAINT corrective_actions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.dg_entries
    ADD CONSTRAINT dg_entries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.regulatory_sources
    ADD CONSTRAINT regulatory_sources_code_key UNIQUE (code);

ALTER TABLE ONLY public.regulatory_sources
    ADD CONSTRAINT regulatory_sources_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.risk_matrices
    ADD CONSTRAINT risk_matrices_name_key UNIQUE (name);

ALTER TABLE ONLY public.risk_matrices
    ADD CONSTRAINT risk_matrices_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.rule_tables
    ADD CONSTRAINT rule_tables_code_key UNIQUE (code);

ALTER TABLE ONLY public.rule_tables
    ADD CONSTRAINT rule_tables_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT stored_files_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.dg_entries
    ADD CONSTRAINT uq_entry_variant UNIQUE (source_id, un_number, variant);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

CREATE INDEX ix_approvals_report_id ON public.approvals USING btree (report_id);

CREATE INDEX ix_audit_log_action ON public.audit_log USING btree (action);

CREATE INDEX ix_corrective_actions_report_id ON public.corrective_actions USING btree (report_id);

CREATE INDEX ix_dg_entries_source_id ON public.dg_entries USING btree (source_id);

CREATE INDEX ix_dg_entries_un_number ON public.dg_entries USING btree (un_number);

CREATE INDEX ix_reports_kind ON public.reports USING btree (kind);

CREATE INDEX ix_stored_files_sha256 ON public.stored_files USING btree (sha256);

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);

CREATE TRIGGER audit_no_modify BEFORE DELETE OR UPDATE ON public.audit_log FOR EACH ROW EXECUTE FUNCTION public.audit_log_block();

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id);

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.corrective_actions
    ADD CONSTRAINT corrective_actions_closed_by_fkey FOREIGN KEY (closed_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.corrective_actions
    ADD CONSTRAINT corrective_actions_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id);

ALTER TABLE ONLY public.dg_entries
    ADD CONSTRAINT dg_entries_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.regulatory_sources(id);

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.rule_tables
    ADD CONSTRAINT rule_tables_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.regulatory_sources(id);

ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT stored_files_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id);


