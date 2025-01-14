import itertools
import time
import arrow
import sqlalchemy as sa
from sqlalchemy.orm import scoped_session, sessionmaker

from baselayer.app.env import load_env
from baselayer.app.models import init_db
from baselayer.log import make_log
from skyportal.handlers.api.observation_plan import post_survey_efficiency_analysis
from skyportal.models import (
    DBSession,
    DefaultObservationPlanRequest,
    EventObservationPlan,
    ObservationPlanRequest,
)

env, cfg = load_env()
log = make_log('observation_plan_queue')

init_db(**cfg['database'])

Session = scoped_session(sessionmaker())


class ObservationPlanQueue:
    def __init__(self):
        self.scoped_session = scoped_session(sessionmaker())

    def Session(self):
        if self.scoped_session.registry.has():
            return self.scoped_session()
        else:
            return self.scoped_session(bind=DBSession.session_factory.kw["bind"])

    def prioritize_requests(self, requests):
        try:
            if (
                len(requests) == 1
            ):  # if there is only one plan in the queue, no need to prioritize
                return 0

            telescopeAllocationLookup = {}
            allocationByPlanLookup = {}

            # we create 2 lookups to avoid repeating some operations like getting the morning and evening for a telescope
            for ii, plan_requests in enumerate(requests):
                for plan in plan_requests:
                    allocation_id = plan.allocation_id
                    if ii not in allocationByPlanLookup.keys():
                        allocationByPlanLookup[ii] = [
                            {
                                "allocation_id": allocation_id,
                                "start_date": plan.payload.get("start_date", None),
                            }
                        ]
                    else:
                        allocationByPlanLookup[ii].append(
                            {
                                "allocation_id": allocation_id,
                                "start_date": plan.payload.get("start_date", None),
                            }
                        )
                    if allocation_id not in telescopeAllocationLookup:
                        telescopeAllocationLookup[
                            allocation_id
                        ] = plan.allocation.instrument.telescope.current_time

            # now we loop over the plans. For plans with multiple plans we pick the allocation with the earliest start date and morning time
            # at the same time, we pick the plan to prioritize
            plan_with_priority = None
            for plan_id, allocationsAndStartDate in allocationByPlanLookup.items():
                if plan_with_priority is None:
                    plan_with_priority = {
                        "plan_id": plan_id,
                        "morning": telescopeAllocationLookup[
                            allocationsAndStartDate[0]["allocation_id"]
                        ]["morning"],
                        "start_date": allocationsAndStartDate[0]["start_date"],
                    }
                earliest = None
                for allocationAndStartDate in allocationsAndStartDate:
                    # find the plan
                    if earliest is None:
                        earliest = allocationAndStartDate
                        continue
                    if (
                        telescopeAllocationLookup[
                            allocationAndStartDate["allocation_id"]
                        ]["morning"]
                        is False
                    ):
                        continue
                    start_date = allocationAndStartDate["start_date"]
                    if start_date is None:
                        continue
                    start_date = arrow.get(start_date).datetime
                    if (
                        start_date
                        > telescopeAllocationLookup[
                            allocationAndStartDate["allocation_id"]
                        ]["morning"].datetime
                    ):
                        continue
                    if (
                        telescopeAllocationLookup[earliest["allocation_id"]]["morning"]
                        is False
                    ):
                        earliest = allocationAndStartDate
                        continue
                    if (
                        telescopeAllocationLookup[
                            allocationAndStartDate["allocation_id"]
                        ]["morning"].datetime
                        < telescopeAllocationLookup[earliest["allocation_id"]][
                            "morning"
                        ].datetime
                    ):
                        earliest = plan.allocation
                        continue
                allocationByPlanLookup[plan_id] = [earliest]

                # check if that plan is more urgent than the current plan_with_priority
                if (
                    telescopeAllocationLookup[earliest["allocation_id"]]["morning"]
                    is None
                ):
                    continue
                if plan_with_priority["morning"] is None:
                    plan_with_priority = {
                        "plan_id": plan_id,
                        "morning": telescopeAllocationLookup[earliest["allocation_id"]][
                            "morning"
                        ],
                        "start_date": earliest["start_date"],
                    }
                    continue
                if (
                    telescopeAllocationLookup[earliest["allocation_id"]]["morning"]
                    <= plan_with_priority["morning"]
                    and earliest["start_date"] < plan_with_priority["start_date"]
                ):
                    plan_with_priority = {
                        "plan_id": plan_id,
                        "morning": telescopeAllocationLookup[earliest["allocation_id"]][
                            "morning"
                        ],
                        "start_date": earliest["start_date"],
                    }
                    continue

            return plan_with_priority["plan_id"]
        except Exception as e:
            log(f"Error occured prioritizing the observation plan queue: {e}")
            return 0

    def service(self):
        log("Starting observation plan queue.")
        while True:
            with self.Session() as session:
                try:
                    stmt = sa.select(ObservationPlanRequest).where(
                        ObservationPlanRequest.status == "pending submission",
                        ObservationPlanRequest.created_at
                        > arrow.utcnow().shift(days=-1).datetime,
                        # we only want to process plans that have been created in the last 24 hours
                    )
                    single_requests = session.execute(stmt).scalars().unique().all()

                    # requests is a list. We want to group that list of plans to be a list of list,
                    # we group based on the plans 'combined_id' which is a unique uuid for a group of plans
                    # plans that are not grouped simply don't have one
                    combined_requests = [
                        request
                        for request in single_requests
                        if request.combined_id is not None
                    ]
                    requests = [
                        list(group)
                        for _, group in itertools.groupby(
                            combined_requests, lambda x: x.combined_id
                        )
                    ] + [
                        [request]
                        for request in single_requests
                        if request.combined_id is None
                    ]

                    if len(requests) == 0:
                        time.sleep(2)
                        continue

                    log(f"Prioritizing {len(requests)} observation plan requests...")

                    index = self.prioritize_requests(requests)

                    plan_requests = requests[index]
                    plan_ids = []
                    if len(plan_requests) == 1:
                        plan_request = plan_requests[0]
                        try:
                            plan_id = plan_request.allocation.instrument.api_class_obsplan.submit(
                                plan_request.id, asynchronous=False
                            )
                            plan_ids.append(plan_id)
                        except Exception as e:
                            plan_request.status = 'failed to process'
                            log(f'Error processing observation plan: {e.args[0]}')
                            session.commit()
                            time.sleep(2)
                            continue
                        plan_request.status = 'complete'
                        session.commit()

                    else:
                        try:
                            plan_ids = plan_requests[
                                0
                            ].allocation.instrument.api_class_obsplan.submit_multiple(
                                plan_requests, asynchronous=False
                            )
                        except Exception as e:
                            for plan_request in plan_requests:
                                plan_request.status = 'failed to process'
                            log(
                                f'Error processing combined plans: {[plan_request.id for plan_request in plan_requests]}: {str(e)}'
                            )
                            session.commit()
                            time.sleep(2)
                            continue

                        for plan_request in plan_requests:
                            plan_request.status = 'complete'
                        session.commit()

                    log(f"Generated plans: {plan_ids}")
                    for id in plan_ids:
                        try:
                            plan = session.scalars(
                                sa.select(EventObservationPlan).where(
                                    EventObservationPlan.id == int(id)
                                )
                            ).first()
                            default = plan.observation_plan_request.payload.get(
                                'default', None
                            )
                            if default is not None:
                                defaultobsplanrequest = session.scalars(
                                    sa.select(DefaultObservationPlanRequest).where(
                                        DefaultObservationPlanRequest.id == int(default)
                                    )
                                ).first()
                                if defaultobsplanrequest is not None:
                                    for (
                                        default_survey_efficiency
                                    ) in (
                                        defaultobsplanrequest.default_survey_efficiencies
                                    ):
                                        post_survey_efficiency_analysis(
                                            default_survey_efficiency.to_dict(),
                                            plan.id,
                                            1,
                                            session,
                                            asynchronous=False,
                                        )
                        except Exception as e:
                            log(
                                f"Error occured processing default survey efficiency for plan {id}: {e}"
                            )
                            session.rollback()
                            time.sleep(2)

                except Exception as e:
                    log(f"Error occured processing the observation plan queue: {e}")
                    session.rollback()
                    time.sleep(2)


if __name__ == "__main__":
    try:
        queue = ObservationPlanQueue()
        queue.service()
    except Exception as e:
        log(f"Error starting observation plan queue: {str(e)}")
        raise e
