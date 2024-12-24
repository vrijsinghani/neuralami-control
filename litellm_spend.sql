#litellm PostgreSQL
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

CREATE VIEW public."Last30dModelsBySpend" AS
 SELECT "LiteLLM_SpendLogs".model,
    sum("LiteLLM_SpendLogs".spend) AS total_spend
   FROM public."LiteLLM_SpendLogs"
  WHERE (("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval)) AND ("LiteLLM_SpendLogs".model <> ''::text))
  GROUP BY "LiteLLM_SpendLogs".model
  ORDER BY (sum("LiteLLM_SpendLogs".spend)) DESC;


CREATE VIEW public."Last30dTopEndUsersSpend" AS
 SELECT "LiteLLM_SpendLogs".end_user,
    count(*) AS total_events,
    sum("LiteLLM_SpendLogs".spend) AS total_spend
   FROM public."LiteLLM_SpendLogs"
  WHERE (("LiteLLM_SpendLogs".end_user <> ''::text) AND ("LiteLLM_SpendLogs".end_user <> USER) AND ("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval)))
  GROUP BY "LiteLLM_SpendLogs".end_user
  ORDER BY (sum("LiteLLM_SpendLogs".spend)) DESC
 LIMIT 100;

CREATE VIEW public."MonthlyGlobalSpend" AS
 SELECT date("LiteLLM_SpendLogs"."startTime") AS date,
    sum("LiteLLM_SpendLogs".spend) AS spend
   FROM public."LiteLLM_SpendLogs"
  WHERE ("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval))
  GROUP BY (date("LiteLLM_SpendLogs"."startTime"));

CREATE VIEW public."MonthlyGlobalSpendPerKey" AS
 SELECT date("LiteLLM_SpendLogs"."startTime") AS date,
    sum("LiteLLM_SpendLogs".spend) AS spend,
    "LiteLLM_SpendLogs".api_key
   FROM public."LiteLLM_SpendLogs"
  WHERE ("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval))
  GROUP BY (date("LiteLLM_SpendLogs"."startTime")), "LiteLLM_SpendLogs".api_key;

CREATE VIEW public."MonthlyGlobalSpendPerUserPerKey" AS
 SELECT date("LiteLLM_SpendLogs"."startTime") AS date,
    sum("LiteLLM_SpendLogs".spend) AS spend,
    "LiteLLM_SpendLogs".api_key,
    "LiteLLM_SpendLogs"."user"
   FROM public."LiteLLM_SpendLogs"
  WHERE ("LiteLLM_SpendLogs"."startTime" >= (CURRENT_DATE - '30 days'::interval))
  GROUP BY (date("LiteLLM_SpendLogs"."startTime")), "LiteLLM_SpendLogs"."user", "LiteLLM_SpendLogs".api_key;

CREATE VIEW public.dailytagspend AS
 SELECT jsonb_array_elements_text(s.request_tags) AS individual_request_tag,
    date(s."startTime") AS spend_date,
    count(*) AS log_count,
    sum(s.spend) AS total_spend
   FROM public."LiteLLM_SpendLogs" s
  GROUP BY (jsonb_array_elements_text(s.request_tags)), (date(s."startTime"));

