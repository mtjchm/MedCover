  ## MedCover Planner app


### Overall Idea
- a web application for planning medical cover for events
- developed by and to be primarily used by the Czech Red Cross organization
- the app shall replace the current Google Sheets app that is used for the same purpose and is reaching its limits
- the app shall meet all the current requirements and allow seamless transition


### Functional Requirements
Users administration:
    - app roles (authorization) - admin, coordinator, member, viewer
    - qualification - doctor, SZP, zdravotnik, zelenac (trainee)
    - training/certification - driver, humanitarian unit training, PSP training, etc.
    - member equipment - uniform assigned, etc.
    - phone number, email
    - reporting/overview section - overview of hours worked, planned, nearest registered event, last registered event, etc.
- Master Event (ME):
    - an event (dozor) is typically an individual happening, but there may cases where the cultural/sports event is too large, is happening over several days and on multiple places in parallel. In such cases it is needed to categorize the events (dozory) under an overarching entity. Let's call it a Master Event. By default, a newly created event will fall under the "general" category (běžný dozor). But the admis/coordinators will be able to create new MEs (corresponding to the large music festivals, sports events etc.). This should allow the coordinators to better organize the large events.
    - The ME view should provide an overview of all the events (dozory) that belong to this ME, registratinon status, worked hours, number of finished events, canceled events, open events, etc. For the General ME this shall provide the yearly overview of the medical cover operations.
- Event
    - Each event shall have a lifecycle
        - Draft
        - Published
        - Registration Open
        - Registration Closed
        - Staffed
        - Completed
        - Cancelled
    - Event management - Create, modify, cancel events
    - parametrize events
        - start date,
        - start time,
        - end date,
        - end time,
        - number of patrols (hlídky zdravotníků) - 1 as a default, but can be more
        - required personnel (how many of each qualification or training kind are needed - for example 1 zdravotnik who is also a driver, 2 trainees). typically one patrol is one zdravotnik and one trainee,
        - required equipment (ambulance, tent, PR material, etc.),
        - optional parameter for setting maximum personnel of each qualification or training
        - paid or unpaid event
        - date/time of registration opening ("immediately" being the default) - some events can be active but not open for registration
        - contact person, event address
    - The Responsible Person mechanism:
        - Each event shall have a Responsible Person (RP) assigned before the event start date/time.
        - Typically the first zdravotnik who registers to an event becomes the RP.
        - The RP can be assigned or changed by the coordinator/admin
        - Once the RP is assigned, he/she is responsible for managing the other personnel on that event.
        - If someone removes his/her's registration from an event, the RP will be notified (or it may require RP's approval - to be decided)
        - If the event is nearing its start and it's still not fully occupied, the RP shall get an email notification
        - On events that belong to a custom ME (for example large music festivals), the ME coordinator may force becoming the RP for all the events in this ME, allowing the coordinator to have overall control of the ME
        - The RP shall be notified about changes in the event, for example users switching spots, or coordinator/admin changing some parameters of the event
    - The users registered to an event shall have an option to transfer the registration to a different user (typical scenario is that the user will get sick and will agree with ta colleague to step in)
- Equipment
    - create, modify, delete equipment types (such as AED, medikit etc.),
    - manage Locations
        - create, modify, delete
        - location has a name and description
    - manage equipment inventory
        - item name, item type
        - item location - can be a defined Location (such as the storage room), an event (when the item is used on an event) or a person (if someone picked up the item for an event etc.). The logic of intem current placement handling may change in the future and it is currently not a critical part of the application.
- All objects inthe application (such as Equipment, Event, Master Event, User) shall have permission objects assigned to it. This will allow granular permissions assignment to user roles.
    - Example permissions:
        user.view
        user.edit
        event.create
        event.edit
        event.cancel
        event.publish
        event.assign
        event.set_responsible_person
        equipment_type.view
        equipment_type.edit
        equipment_type.create
        audit.view
        notification.send
        master_event.view
        master_event.edit
        master_event.create
        master_event.cancel
        master_event.assign
- The app must be accessible via Internet
- The app must have authentication
- Display the events in a form of a table or calendar
- Email notifications and reminders (individual users can set their own reminers for events they have subscribed in, admins can send emails to remind selected roles that they are needed for events that are not fully occupied)
- Notifications should be customizable to prevent unnecessary spamming (possible customization on the level of the ME, Event,...)
- Audit capability (view changes for individual entities, app configuration etc.)


### Non-Functional Requirements
- The app must be user friendly and very easy to use - not all users are very skilled at IT
- There should be tooltips helping users use the app
- The app must be available 24/7
- The app UI must be in Czech language
- all changes must be logged and allow auditing - who changed what and when
- The infrastructure used by the app should allow backup/restore of the app. Daily backups with 60 days retention, 1day RPO, 12 hours RTO


### Ideas for future
- Feature to manage not only medical cover but also medical training events with its specific requirements


### Architectural Decisions
- AD01 User Roles Customization
    - Problem statement - Should the user roles be hardcoded or customizable?
    - Decision - Hardcoded pre-defined roles, adding custom roles may be added to the app later
    - Justification - app roles are sets of permissions such as:
            user.view
            user.edit
            event.create
            event.edit
            event.cancel
            event.publish
            event.assign
            event.set_responsible_person
        they are relatively stable and allow good testing. Custom roles may be added to the app later but at this point, for simplicity, only pre-defined roles will be used.
