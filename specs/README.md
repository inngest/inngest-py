# v0.6 specs

## Foundation

This diagram is derived from each spec's `### Blocking` section.

```mermaid
flowchart LR
    subgraph serialization["Serialization"]
        infer_output_types["Infer output types for custom serialization<br/>[Typing]"]
        payload_serializers["Add payload serializer pipeline<br/>[Architecture]"]
        pydantic_serialization["Enable Pydantic serialization by default<br/>[Quality of life]"]
        remove_json["Remove the public `JSON` type alias<br/>[Typing]"]
    end

    subgraph config["Config"]
        enable_unauthed_sync["Default unauthenticated sync to disabled<br/>[Security]"]
        int_duration["Require `datetime.timedelta` for duration parameters<br/>[Quality of life]"]
        is_production["Rename `is_production` to `is_dev`<br/>[Quality of life]"]
        streaming["Replace `Streaming` enum with a FastAPI `streaming` option<br/>[Quality of life]"]
    end

    subgraph events["Events"]
        separate_events["Split send-side `Event` from receive-side `ReceivedEvent`<br/>[Architecture]"]
        typed_event_input["Typed event input data<br/>[Typing]"]
    end

    subgraph execution["Execution"]
        retry_control_flow_errors["Retry control-flow errors become step interrupts<br/>[Correctness]"]
    end

    subgraph logging["Logging"]
        sdk_log_extra_fields["Standardize SDK log `extra` fields<br/>[Observability]"]
        separate_logging["Separate SDK-internal logging from function logging<br/>[Observability]"]
        use_logging_filter["Replace replay logger wrapper with a `logging.Filter`<br/>[Observability]"]
    end

    subgraph middleware["Middleware"]
        context_ext["Add `ctx.ext`<br/>[Architecture]"]
        rewrite_middleware["Rewrite middleware<br/>[Architecture]"]
    end

    subgraph packaging["Packaging"]
        update_dependencies["Update dependencies<br/>[Maintenance]"]
    end

    infer_output_types --> pydantic_serialization
    payload_serializers --> infer_output_types
    payload_serializers --> pydantic_serialization
    remove_json --> pydantic_serialization

    separate_events --> typed_event_input
    remove_json --> separate_events
    remove_json --> typed_event_input
    payload_serializers --> typed_event_input
    pydantic_serialization --> typed_event_input

    separate_logging --> sdk_log_extra_fields
    separate_logging --> use_logging_filter

    rewrite_middleware --> context_ext

    classDef architecture fill:#e0e7ff,stroke:#4f46e5,color:#111827
    classDef correctness fill:#fee2e2,stroke:#dc2626,color:#111827
    classDef observability fill:#dcfce7,stroke:#16a34a,color:#111827
    classDef quality fill:#fef3c7,stroke:#d97706,color:#111827
    classDef maintenance fill:#f3f4f6,stroke:#6b7280,color:#111827
    classDef security fill:#fce7f3,stroke:#be185d,color:#111827
    classDef typing fill:#e0f2fe,stroke:#0284c7,color:#111827

    class context_ext,payload_serializers,rewrite_middleware,separate_events architecture
    class retry_control_flow_errors correctness
    class update_dependencies maintenance
    class sdk_log_extra_fields,separate_logging,use_logging_filter observability
    class int_duration,is_production,pydantic_serialization,streaming quality
    class enable_unauthed_sync security
    class infer_output_types,remove_json,typed_event_input typing
```

Arrows point from blocking prerequisite to dependent spec.

# TypeScript SDK parity

No specs yet.

- Checkpointing
- Deferred functions
- Experiments
- Metadata
- Scoring
- OTel AI metadata extraction
