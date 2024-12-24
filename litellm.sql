--
-- PostgreSQL database dump
--

-- Dumped from database version 13.18 (Debian 13.18-1.pgdg120+1)
-- Dumped by pg_dump version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
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
-- Name: LiteLLM_SpendLogs; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_SpendLogs" (
    request_id text NOT NULL,
    call_type text NOT NULL,
    api_key text DEFAULT ''::text NOT NULL,
    spend double precision DEFAULT 0.0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    prompt_tokens integer DEFAULT 0 NOT NULL,
    completion_tokens integer DEFAULT 0 NOT NULL,
    "startTime" timestamp(3) without time zone NOT NULL,
    "endTime" timestamp(3) without time zone NOT NULL,
    "completionStartTime" timestamp(3) without time zone,
    model text DEFAULT ''::text NOT NULL,
    model_id text DEFAULT ''::text,
    model_group text DEFAULT ''::text,
    api_base text DEFAULT ''::text,
    "user" text DEFAULT ''::text,
    metadata jsonb DEFAULT '{}'::jsonb,
    cache_hit text DEFAULT ''::text,
    cache_key text DEFAULT ''::text,
    request_tags jsonb DEFAULT '[]'::jsonb,
    team_id text,
    end_user text,
    requester_ip_address text
);


ALTER TABLE public."LiteLLM_SpendLogs" OWNER TO litellmuser;

--
-- Name: LiteLLM_VerificationToken; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_VerificationToken" (
    token text NOT NULL,
    key_name text,
    key_alias text,
    soft_budget_cooldown boolean DEFAULT false NOT NULL,
    spend double precision DEFAULT 0.0 NOT NULL,
    expires timestamp(3) without time zone,
    models text[],
    aliases jsonb DEFAULT '{}'::jsonb NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    user_id text,
    team_id text,
    permissions jsonb DEFAULT '{}'::jsonb NOT NULL,
    max_parallel_requests integer,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    blocked boolean,
    tpm_limit bigint,
    rpm_limit bigint,
    max_budget double precision,
    budget_duration text,
    budget_reset_at timestamp(3) without time zone,
    allowed_cache_controls text[] DEFAULT ARRAY[]::text[],
    model_spend jsonb DEFAULT '{}'::jsonb NOT NULL,
    model_max_budget jsonb DEFAULT '{}'::jsonb NOT NULL,
    budget_id text,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public."LiteLLM_VerificationToken" OWNER TO litellmuser;

--
-- Name: Last30dKeysBySpend; Type: VIEW; Schema: public; Owner: litellmuser
--

CREATE VIEW public."Last30dKeysBySpend" AS
 SELECT l.api_key,
    v.key_alias,
    v.key_name,
    sum(l.spend) AS total_spend
   FROM (public."LiteLLM_SpendLogs" l
     LEFT JOIN public."LiteLLM_VerificationToken" v ON ((l.api_key = v.token)))
  WHERE (l."startTime" >= (CURRENT_DATE - '30 days'::interval))
  GROUP BY l.api_key, v.key_alias, v.key_name
  ORDER BY (sum(l.spend)) DESC;


ALTER TABLE public."Last30dKeysBySpend" OWNER TO litellmuser;

--
-- Name: Last30dModelsBySpend; Type: VIEW; Schema: public; Owner: litellmuser
--

CREATE VIEW public."Last30dModelsBySpend" AS
 SELECT "LiteLLM_SpendLogs".model,
    sum("LiteLLM_SpendLogs".spend) AS total_spend
   FROM public."LiteLLM_SpendLogs"
  WHERE (("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval)) AND ("LiteLLM_SpendLogs".model <> ''::text))
  GROUP BY "LiteLLM_SpendLogs".model
  ORDER BY (sum("LiteLLM_SpendLogs".spend)) DESC;


ALTER TABLE public."Last30dModelsBySpend" OWNER TO litellmuser;

--
-- Name: Last30dTopEndUsersSpend; Type: VIEW; Schema: public; Owner: litellmuser
--

CREATE VIEW public."Last30dTopEndUsersSpend" AS
 SELECT "LiteLLM_SpendLogs".end_user,
    count(*) AS total_events,
    sum("LiteLLM_SpendLogs".spend) AS total_spend
   FROM public."LiteLLM_SpendLogs"
  WHERE (("LiteLLM_SpendLogs".end_user <> ''::text) AND ("LiteLLM_SpendLogs".end_user <> USER) AND ("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval)))
  GROUP BY "LiteLLM_SpendLogs".end_user
  ORDER BY (sum("LiteLLM_SpendLogs".spend)) DESC
 LIMIT 100;


ALTER TABLE public."Last30dTopEndUsersSpend" OWNER TO litellmuser;

--
-- Name: LiteLLM_AuditLog; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_AuditLog" (
    id text NOT NULL,
    updated_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    changed_by text DEFAULT ''::text NOT NULL,
    changed_by_api_key text DEFAULT ''::text NOT NULL,
    action text NOT NULL,
    table_name text NOT NULL,
    object_id text NOT NULL,
    before_value jsonb,
    updated_values jsonb
);


ALTER TABLE public."LiteLLM_AuditLog" OWNER TO litellmuser;

--
-- Name: LiteLLM_BudgetTable; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_BudgetTable" (
    budget_id text NOT NULL,
    max_budget double precision,
    soft_budget double precision,
    max_parallel_requests integer,
    tpm_limit bigint,
    rpm_limit bigint,
    model_max_budget jsonb,
    budget_duration text,
    budget_reset_at timestamp(3) without time zone,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by text NOT NULL,
    updated_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by text NOT NULL
);


ALTER TABLE public."LiteLLM_BudgetTable" OWNER TO litellmuser;

--
-- Name: LiteLLM_Config; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_Config" (
    param_name text NOT NULL,
    param_value jsonb
);


ALTER TABLE public."LiteLLM_Config" OWNER TO litellmuser;

--
-- Name: LiteLLM_EndUserTable; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_EndUserTable" (
    user_id text NOT NULL,
    alias text,
    spend double precision DEFAULT 0.0 NOT NULL,
    allowed_model_region text,
    default_model text,
    budget_id text,
    blocked boolean DEFAULT false NOT NULL
);


ALTER TABLE public."LiteLLM_EndUserTable" OWNER TO litellmuser;

--
-- Name: LiteLLM_ErrorLogs; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_ErrorLogs" (
    request_id text NOT NULL,
    "startTime" timestamp(3) without time zone NOT NULL,
    "endTime" timestamp(3) without time zone NOT NULL,
    api_base text DEFAULT ''::text NOT NULL,
    model_group text DEFAULT ''::text NOT NULL,
    litellm_model_name text DEFAULT ''::text NOT NULL,
    model_id text DEFAULT ''::text NOT NULL,
    request_kwargs jsonb DEFAULT '{}'::jsonb NOT NULL,
    exception_type text DEFAULT ''::text NOT NULL,
    exception_string text DEFAULT ''::text NOT NULL,
    status_code text DEFAULT ''::text NOT NULL
);


ALTER TABLE public."LiteLLM_ErrorLogs" OWNER TO litellmuser;

--
-- Name: LiteLLM_InvitationLink; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_InvitationLink" (
    id text NOT NULL,
    user_id text NOT NULL,
    is_accepted boolean DEFAULT false NOT NULL,
    accepted_at timestamp(3) without time zone,
    expires_at timestamp(3) without time zone NOT NULL,
    created_at timestamp(3) without time zone NOT NULL,
    created_by text NOT NULL,
    updated_at timestamp(3) without time zone NOT NULL,
    updated_by text NOT NULL
);


ALTER TABLE public."LiteLLM_InvitationLink" OWNER TO litellmuser;

--
-- Name: LiteLLM_ModelTable; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_ModelTable" (
    id integer NOT NULL,
    aliases jsonb,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by text NOT NULL,
    updated_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by text NOT NULL
);


ALTER TABLE public."LiteLLM_ModelTable" OWNER TO litellmuser;

--
-- Name: LiteLLM_ModelTable_id_seq; Type: SEQUENCE; Schema: public; Owner: litellmuser
--

CREATE SEQUENCE public."LiteLLM_ModelTable_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public."LiteLLM_ModelTable_id_seq" OWNER TO litellmuser;

--
-- Name: LiteLLM_ModelTable_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: litellmuser
--

ALTER SEQUENCE public."LiteLLM_ModelTable_id_seq" OWNED BY public."LiteLLM_ModelTable".id;


--
-- Name: LiteLLM_OrganizationMembership; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_OrganizationMembership" (
    user_id text NOT NULL,
    organization_id text NOT NULL,
    user_role text,
    spend double precision DEFAULT 0.0,
    budget_id text,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public."LiteLLM_OrganizationMembership" OWNER TO litellmuser;

--
-- Name: LiteLLM_OrganizationTable; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_OrganizationTable" (
    organization_id text NOT NULL,
    organization_alias text NOT NULL,
    budget_id text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    models text[],
    spend double precision DEFAULT 0.0 NOT NULL,
    model_spend jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by text NOT NULL,
    updated_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by text NOT NULL
);


ALTER TABLE public."LiteLLM_OrganizationTable" OWNER TO litellmuser;

--
-- Name: LiteLLM_ProxyModelTable; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_ProxyModelTable" (
    model_id text NOT NULL,
    model_name text NOT NULL,
    litellm_params jsonb NOT NULL,
    model_info jsonb,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by text NOT NULL,
    updated_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by text NOT NULL
);


ALTER TABLE public."LiteLLM_ProxyModelTable" OWNER TO litellmuser;

--
-- Name: LiteLLM_TeamMembership; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_TeamMembership" (
    user_id text NOT NULL,
    team_id text NOT NULL,
    spend double precision DEFAULT 0.0 NOT NULL,
    budget_id text
);


ALTER TABLE public."LiteLLM_TeamMembership" OWNER TO litellmuser;

--
-- Name: LiteLLM_TeamTable; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_TeamTable" (
    team_id text NOT NULL,
    team_alias text,
    organization_id text,
    admins text[],
    members text[],
    members_with_roles jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    max_budget double precision,
    spend double precision DEFAULT 0.0 NOT NULL,
    models text[],
    max_parallel_requests integer,
    tpm_limit bigint,
    rpm_limit bigint,
    budget_duration text,
    budget_reset_at timestamp(3) without time zone,
    blocked boolean DEFAULT false NOT NULL,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    model_spend jsonb DEFAULT '{}'::jsonb NOT NULL,
    model_max_budget jsonb DEFAULT '{}'::jsonb NOT NULL,
    model_id integer
);


ALTER TABLE public."LiteLLM_TeamTable" OWNER TO litellmuser;

--
-- Name: LiteLLM_UserNotifications; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_UserNotifications" (
    request_id text NOT NULL,
    user_id text NOT NULL,
    models text[],
    justification text NOT NULL,
    status text NOT NULL
);


ALTER TABLE public."LiteLLM_UserNotifications" OWNER TO litellmuser;

--
-- Name: LiteLLM_UserTable; Type: TABLE; Schema: public; Owner: litellmuser
--

CREATE TABLE public."LiteLLM_UserTable" (
    user_id text NOT NULL,
    user_alias text,
    team_id text,
    organization_id text,
    password text,
    teams text[] DEFAULT ARRAY[]::text[],
    user_role text,
    max_budget double precision,
    spend double precision DEFAULT 0.0 NOT NULL,
    user_email text,
    models text[],
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    max_parallel_requests integer,
    tpm_limit bigint,
    rpm_limit bigint,
    budget_duration text,
    budget_reset_at timestamp(3) without time zone,
    allowed_cache_controls text[] DEFAULT ARRAY[]::text[],
    model_spend jsonb DEFAULT '{}'::jsonb NOT NULL,
    model_max_budget jsonb DEFAULT '{}'::jsonb NOT NULL
);


ALTER TABLE public."LiteLLM_UserTable" OWNER TO litellmuser;

--
-- Name: LiteLLM_VerificationTokenView; Type: VIEW; Schema: public; Owner: litellmuser
--

CREATE VIEW public."LiteLLM_VerificationTokenView" AS
 SELECT v.token,
    v.key_name,
    v.key_alias,
    v.soft_budget_cooldown,
    v.spend,
    v.expires,
    v.models,
    v.aliases,
    v.config,
    v.user_id,
    v.team_id,
    v.permissions,
    v.max_parallel_requests,
    v.metadata,
    v.blocked,
    v.tpm_limit,
    v.rpm_limit,
    v.max_budget,
    v.budget_duration,
    v.budget_reset_at,
    v.allowed_cache_controls,
    v.model_spend,
    v.model_max_budget,
    v.budget_id,
    v.created_at,
    v.updated_at,
    t.spend AS team_spend,
    t.max_budget AS team_max_budget,
    t.tpm_limit AS team_tpm_limit,
    t.rpm_limit AS team_rpm_limit
   FROM (public."LiteLLM_VerificationToken" v
     LEFT JOIN public."LiteLLM_TeamTable" t ON ((v.team_id = t.team_id)));


ALTER TABLE public."LiteLLM_VerificationTokenView" OWNER TO litellmuser;

--
-- Name: MonthlyGlobalSpend; Type: VIEW; Schema: public; Owner: litellmuser
--

CREATE VIEW public."MonthlyGlobalSpend" AS
 SELECT date("LiteLLM_SpendLogs"."startTime") AS date,
    sum("LiteLLM_SpendLogs".spend) AS spend
   FROM public."LiteLLM_SpendLogs"
  WHERE ("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval))
  GROUP BY (date("LiteLLM_SpendLogs"."startTime"));


ALTER TABLE public."MonthlyGlobalSpend" OWNER TO litellmuser;

--
-- Name: MonthlyGlobalSpendPerKey; Type: VIEW; Schema: public; Owner: litellmuser
--

CREATE VIEW public."MonthlyGlobalSpendPerKey" AS
 SELECT date("LiteLLM_SpendLogs"."startTime") AS date,
    sum("LiteLLM_SpendLogs".spend) AS spend,
    "LiteLLM_SpendLogs".api_key
   FROM public."LiteLLM_SpendLogs"
  WHERE ("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval))
  GROUP BY (date("LiteLLM_SpendLogs"."startTime")), "LiteLLM_SpendLogs".api_key;


ALTER TABLE public."MonthlyGlobalSpendPerKey" OWNER TO litellmuser;

--
-- Name: MonthlyGlobalSpendPerUserPerKey; Type: VIEW; Schema: public; Owner: litellmuser
--

CREATE VIEW public."MonthlyGlobalSpendPerUserPerKey" AS
 SELECT date("LiteLLM_SpendLogs"."startTime") AS date,
    sum("LiteLLM_SpendLogs".spend) AS spend,
    "LiteLLM_SpendLogs".api_key,
    "LiteLLM_SpendLogs"."user"
   FROM public."LiteLLM_SpendLogs"
  WHERE ("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval))
  GROUP BY (date("LiteLLM_SpendLogs"."startTime")), "LiteLLM_SpendLogs"."user", "LiteLLM_SpendLogs".api_key;


ALTER TABLE public."MonthlyGlobalSpendPerUserPerKey" OWNER TO litellmuser;

--
-- Name: dailytagspend; Type: VIEW; Schema: public; Owner: litellmuser
--

CREATE VIEW public.dailytagspend AS
 SELECT jsonb_array_elements_text(s.request_tags) AS individual_request_tag,
    date(s."startTime") AS spend_date,
    count(*) AS log_count,
    sum(s.spend) AS total_spend
   FROM public."LiteLLM_SpendLogs" s
  GROUP BY (jsonb_array_elements_text(s.request_tags)), (date(s."startTime"));


ALTER TABLE public.dailytagspend OWNER TO litellmuser;

--
-- Name: LiteLLM_ModelTable id; Type: DEFAULT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_ModelTable" ALTER COLUMN id SET DEFAULT nextval('public."LiteLLM_ModelTable_id_seq"'::regclass);


--
-- Name: LiteLLM_AuditLog LiteLLM_AuditLog_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_AuditLog"
    ADD CONSTRAINT "LiteLLM_AuditLog_pkey" PRIMARY KEY (id);


--
-- Name: LiteLLM_BudgetTable LiteLLM_BudgetTable_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_BudgetTable"
    ADD CONSTRAINT "LiteLLM_BudgetTable_pkey" PRIMARY KEY (budget_id);


--
-- Name: LiteLLM_Config LiteLLM_Config_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_Config"
    ADD CONSTRAINT "LiteLLM_Config_pkey" PRIMARY KEY (param_name);


--
-- Name: LiteLLM_EndUserTable LiteLLM_EndUserTable_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_EndUserTable"
    ADD CONSTRAINT "LiteLLM_EndUserTable_pkey" PRIMARY KEY (user_id);


--
-- Name: LiteLLM_ErrorLogs LiteLLM_ErrorLogs_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_ErrorLogs"
    ADD CONSTRAINT "LiteLLM_ErrorLogs_pkey" PRIMARY KEY (request_id);


--
-- Name: LiteLLM_InvitationLink LiteLLM_InvitationLink_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_InvitationLink"
    ADD CONSTRAINT "LiteLLM_InvitationLink_pkey" PRIMARY KEY (id);


--
-- Name: LiteLLM_ModelTable LiteLLM_ModelTable_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_ModelTable"
    ADD CONSTRAINT "LiteLLM_ModelTable_pkey" PRIMARY KEY (id);


--
-- Name: LiteLLM_OrganizationMembership LiteLLM_OrganizationMembership_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_OrganizationMembership"
    ADD CONSTRAINT "LiteLLM_OrganizationMembership_pkey" PRIMARY KEY (user_id, organization_id);


--
-- Name: LiteLLM_OrganizationTable LiteLLM_OrganizationTable_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_OrganizationTable"
    ADD CONSTRAINT "LiteLLM_OrganizationTable_pkey" PRIMARY KEY (organization_id);


--
-- Name: LiteLLM_ProxyModelTable LiteLLM_ProxyModelTable_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_ProxyModelTable"
    ADD CONSTRAINT "LiteLLM_ProxyModelTable_pkey" PRIMARY KEY (model_id);


--
-- Name: LiteLLM_SpendLogs LiteLLM_SpendLogs_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_SpendLogs"
    ADD CONSTRAINT "LiteLLM_SpendLogs_pkey" PRIMARY KEY (request_id);


--
-- Name: LiteLLM_TeamMembership LiteLLM_TeamMembership_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_TeamMembership"
    ADD CONSTRAINT "LiteLLM_TeamMembership_pkey" PRIMARY KEY (user_id, team_id);


--
-- Name: LiteLLM_TeamTable LiteLLM_TeamTable_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_TeamTable"
    ADD CONSTRAINT "LiteLLM_TeamTable_pkey" PRIMARY KEY (team_id);


--
-- Name: LiteLLM_UserNotifications LiteLLM_UserNotifications_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_UserNotifications"
    ADD CONSTRAINT "LiteLLM_UserNotifications_pkey" PRIMARY KEY (request_id);


--
-- Name: LiteLLM_UserTable LiteLLM_UserTable_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_UserTable"
    ADD CONSTRAINT "LiteLLM_UserTable_pkey" PRIMARY KEY (user_id);


--
-- Name: LiteLLM_VerificationToken LiteLLM_VerificationToken_pkey; Type: CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_VerificationToken"
    ADD CONSTRAINT "LiteLLM_VerificationToken_pkey" PRIMARY KEY (token);


--
-- Name: LiteLLM_OrganizationMembership_user_id_organization_id_key; Type: INDEX; Schema: public; Owner: litellmuser
--

CREATE UNIQUE INDEX "LiteLLM_OrganizationMembership_user_id_organization_id_key" ON public."LiteLLM_OrganizationMembership" USING btree (user_id, organization_id);


--
-- Name: LiteLLM_SpendLogs_end_user_idx; Type: INDEX; Schema: public; Owner: litellmuser
--

CREATE INDEX "LiteLLM_SpendLogs_end_user_idx" ON public."LiteLLM_SpendLogs" USING btree (end_user);


--
-- Name: LiteLLM_SpendLogs_startTime_idx; Type: INDEX; Schema: public; Owner: litellmuser
--

CREATE INDEX "LiteLLM_SpendLogs_startTime_idx" ON public."LiteLLM_SpendLogs" USING btree ("startTime");


--
-- Name: LiteLLM_TeamTable_model_id_key; Type: INDEX; Schema: public; Owner: litellmuser
--

CREATE UNIQUE INDEX "LiteLLM_TeamTable_model_id_key" ON public."LiteLLM_TeamTable" USING btree (model_id);


--
-- Name: LiteLLM_EndUserTable LiteLLM_EndUserTable_budget_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_EndUserTable"
    ADD CONSTRAINT "LiteLLM_EndUserTable_budget_id_fkey" FOREIGN KEY (budget_id) REFERENCES public."LiteLLM_BudgetTable"(budget_id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: LiteLLM_InvitationLink LiteLLM_InvitationLink_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_InvitationLink"
    ADD CONSTRAINT "LiteLLM_InvitationLink_created_by_fkey" FOREIGN KEY (created_by) REFERENCES public."LiteLLM_UserTable"(user_id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: LiteLLM_InvitationLink LiteLLM_InvitationLink_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_InvitationLink"
    ADD CONSTRAINT "LiteLLM_InvitationLink_updated_by_fkey" FOREIGN KEY (updated_by) REFERENCES public."LiteLLM_UserTable"(user_id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: LiteLLM_InvitationLink LiteLLM_InvitationLink_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_InvitationLink"
    ADD CONSTRAINT "LiteLLM_InvitationLink_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public."LiteLLM_UserTable"(user_id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: LiteLLM_OrganizationMembership LiteLLM_OrganizationMembership_budget_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_OrganizationMembership"
    ADD CONSTRAINT "LiteLLM_OrganizationMembership_budget_id_fkey" FOREIGN KEY (budget_id) REFERENCES public."LiteLLM_BudgetTable"(budget_id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: LiteLLM_OrganizationMembership LiteLLM_OrganizationMembership_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_OrganizationMembership"
    ADD CONSTRAINT "LiteLLM_OrganizationMembership_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public."LiteLLM_UserTable"(user_id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: LiteLLM_OrganizationTable LiteLLM_OrganizationTable_budget_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_OrganizationTable"
    ADD CONSTRAINT "LiteLLM_OrganizationTable_budget_id_fkey" FOREIGN KEY (budget_id) REFERENCES public."LiteLLM_BudgetTable"(budget_id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: LiteLLM_TeamMembership LiteLLM_TeamMembership_budget_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_TeamMembership"
    ADD CONSTRAINT "LiteLLM_TeamMembership_budget_id_fkey" FOREIGN KEY (budget_id) REFERENCES public."LiteLLM_BudgetTable"(budget_id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: LiteLLM_TeamTable LiteLLM_TeamTable_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_TeamTable"
    ADD CONSTRAINT "LiteLLM_TeamTable_model_id_fkey" FOREIGN KEY (model_id) REFERENCES public."LiteLLM_ModelTable"(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: LiteLLM_TeamTable LiteLLM_TeamTable_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_TeamTable"
    ADD CONSTRAINT "LiteLLM_TeamTable_organization_id_fkey" FOREIGN KEY (organization_id) REFERENCES public."LiteLLM_OrganizationTable"(organization_id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: LiteLLM_UserTable LiteLLM_UserTable_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_UserTable"
    ADD CONSTRAINT "LiteLLM_UserTable_organization_id_fkey" FOREIGN KEY (organization_id) REFERENCES public."LiteLLM_OrganizationTable"(organization_id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: LiteLLM_VerificationToken LiteLLM_VerificationToken_budget_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: litellmuser
--

ALTER TABLE ONLY public."LiteLLM_VerificationToken"
    ADD CONSTRAINT "LiteLLM_VerificationToken_budget_id_fkey" FOREIGN KEY (budget_id) REFERENCES public."LiteLLM_BudgetTable"(budget_id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

