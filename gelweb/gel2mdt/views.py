from django.shortcuts import render, redirect
from .forms import *
from .models import *
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError
from datetime import datetime
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.db.models import Q
from .database_utils.multiple_case_adder import MultipleCaseAdder
from .primer_utils import singletarget
from .tasks import get_gel_content, panel_app
from .api.api_views import *
from django.forms import modelformset_factory
from .config import load_config
import os, json, csv
from .exports import write_mdt_outcome_template, write_mdt_export
from io import BytesIO, StringIO
from .vep_utils.run_vep_batch import CaseVariant
from .tasks import VariantAdder
from .database_utils.multiple_case_adder import MultipleCaseAdder
# Create your views here.

def register(request):
    '''
    Registers a new user
    :param request:
    :return:
    '''
    registered = False
    username = ''

    if request.method == 'POST':
        user_form = UserForm(data=request.POST)

        if user_form.is_valid():
            first_name = user_form.cleaned_data['first_name']
            last_name = user_form.cleaned_data['last_name']
            full_name = str(first_name + ' ' + last_name)
            if len(last_name) >= 6:
                username = (last_name[:5] + first_name[0]).lower()
            else:
                username = (last_name + first_name[0]).lower()
            password = user_form.cleaned_data['password']
            email = user_form.cleaned_data['email']
            role = user_form.cleaned_data['role']
            hospital = user_form.cleaned_data['hospital']
            try:
                user = User(username=username, first_name=first_name, last_name=last_name, password=password,
                            email=email, is_active=False)
                user.save()
                user.set_password(user.password)
                user.save()
                registered = True
                if role == 'Clinical Scientist':
                    cs, created = ClinicalScientist.objects.get_or_create(
                        email=email)
                    cs.name = full_name,
                    cs.hospital = hospital
                    cs.save()

                elif role == 'Clinician':
                    clinician, created = Clinician.objects.get_or_create(
                        email=email)
                    clinician.name = full_name
                    clinician.hospital = hospital
                    clinician.added_by_user = True
                    clinician.save()
                elif role == 'Other Staff':
                    other, created = OtherStaff.objects.get_or_create(
                        email=email)
                    other.name = full_name,
                    other.hospital = hospital
                    other.save()
            except IntegrityError:
                messages.error(request, 'If you have already registered, '
                                        'please contact Bioinformatics to activate your account')
                return HttpResponseRedirect('/register')

    else:
        user_form = UserForm()

    return render(request, 'registration/registration.html',
                  {'user_form': user_form, 'registered': registered, 'username': username})


@login_required
def profile(request):
    '''
    Profile page
    :param request:
    :return:
    '''
    role = None
    cs = ClinicalScientist.objects.filter(email=request.user.email).first()
    other = OtherStaff.objects.filter(email=request.user.email).first()
    clinician = Clinician.objects.filter(email=request.user.email).first()

    my_cases = GELInterpretationReport.objects.filter(assigned_user__username=request.user.username)


    if cs:
        rolename = 'Clinical Scientist'
        role = cs
    elif clinician:
        rolename = 'Clinician'
        role = clinician
    elif other:
        rolename = 'Other Staff'
        role = other
    if request.method == 'POST':
        form = ProfileForm(request.POST)
        if form.is_valid():
            if role:
                role.delete() # Delete the old role
            if form.cleaned_data['role'] == 'Clinical Scientist':
                cs = ClinicalScientist(name=request.user.first_name + ' ' + request.user.last_name,
                                       email=request.user.email,
                                       hospital=form.cleaned_data['hospital'])
                cs.save()
            elif form.cleaned_data['role'] == 'Clinician':
                clinician = Clinician(name=request.user.first_name + ' ' + request.user.last_name,
                                      email=request.user.email,
                                      hospital=form.cleaned_data['hospital'],
                                      added_by_user=True)
                clinician.save()
            elif form.cleaned_data['role'] == 'Other Staff':
                other = OtherStaff(name=request.user.first_name + ' ' + request.user.last_name,
                                   email=request.user.email,
                                   hospital=form.cleaned_data['hospital'])
                other.save()
            messages.add_message(request,25, 'Profile Updated')
            return HttpResponseRedirect('/profile')
    else:
        form = ProfileForm(initial={'role': rolename, 'hospital':role.hospital})
    return render(request, 'gel2mdt/profile.html', {'form': form,
                                                    'role':role,
                                                    'my_cases': my_cases,
                                                    'rolename':rolename})

@login_required
def remove_case(request, case_id):

    case = GELInterpretationReport.objects.get(id=case_id)
    case.assigned_user = None
    case.save()

    return redirect('profile')



@login_required
def cancer_main(request):
    '''
    Shows all the Cancer cases the user has access to and allows easy searching of cases
    :param request:
    :return:
    '''
    return render(request, 'gel2mdt/cancer_main.html', {})


@login_required
def rare_disease_main(request):
    '''
    Shows all the RD cases the user has access to and allows easy searching of cases
    :param request:
    :return:
    '''
    rd_case_families = InterpretationReportFamily.objects.prefetch_related().all()
    rd_case_families = [rd_case_family for rd_case_family in rd_case_families]
    rd_cases = [
        GELInterpretationReport.objects.filter(ir_family=ir_family).latest("polled_at_datetime")
        for ir_family in rd_case_families
    ]
    return render(request, 'gel2mdt/rare_disease_main.html', {'rd_cases': rd_cases})

@login_required
def proband_view(request, report_id):
    '''
    Shows details about a particular proband, some fields are editable by clinical scientists
    :param request:
    :param report_id: GEL Report ID
    :return:
    '''

    report = GELInterpretationReport.objects.get(id=report_id)

    # POST request from Demographic Update Form
    if request.method == "POST":
        demogs_form = DemogsForm(request.POST, instance=report.ir_family.participant_family.proband)
        case_assign_form = CaseAssignForm(request.POST, instance=report)
        if demogs_form.is_valid():
            demogs_form.save()
        if case_assign_form.is_valid():
            case_assign_form.save()

    relatives = Relative.objects.filter(proband=report.ir_family.participant_family.proband)
    proband_form = ProbandForm(instance=report.ir_family.participant_family.proband)
    demogs_form = DemogsForm(instance=report.ir_family.participant_family.proband)
    proband_variants = ProbandVariant.objects.filter(interpretation_report=report)
    proband_mdt = MDTReport.objects.filter(interpretation_report=report)
    panels = InterpretationReportFamilyPanel.objects.filter(ir_family=report.ir_family)

    case_assign_form = CaseAssignForm(instance=report)

    if proband_form["status"].value() == "C":
        for field in proband_form.__dict__["fields"]:
            proband_form.fields[field].widget.attrs['readonly'] = True
            proband_form.fields[field].widget.attrs['disabled'] = True

    return render(request, 'gel2mdt/proband.html', {'report': report,
                                                    'relatives': relatives,
                                                    'proband_form': proband_form,
                                                    'demogs_form': demogs_form,
                                                    'case_assign_form': case_assign_form,
                                                    'proband_variants': proband_variants,
                                                    'proband_mdt': proband_mdt,
                                                    'panels': panels})

@login_required
def pull_t3_variants(request, report_id):
    report = GELInterpretationReport.objects.get(id=report_id)
    mca = MultipleCaseAdder(pullt3=True, sample=report.ir_family.participant_family.proband.gel_id)
    mca.update_database()
    return HttpResponseRedirect(f'/proband/{report_id}')


def panel_view(request, panelversion_id):
    panel = PanelVersion.objects.get(id=panelversion_id)
    config_dict = load_config.LoadConfig().load()
    panelapp_file = f'{config_dict["panelapp_storage"]}/{panel.panel.panelapp_id}_{panel.version_number}.json'
    if os.path.isfile(panelapp_file):
        panelapp_json = json.load(open(panelapp_file))
        return render(request, 'gel2mdt/panel.html', {'panel':panel,
                                                      'genes': panelapp_json['result']['Genes']})

@login_required
def variant_view(request, variant_id):
    '''
    Shows details about a particular proband, some fields are editable by clinical scientists
    :param request:
    :param report_id: GEL Report ID
    :return:
    '''
    if request.method == "POST":
        # if not models.objects.filter(gel_id=proband_id):
        print("Designing primers")
        #report_event = ReportEvent.objects.filter(variant=variant_id)
        variant = Variant.objects.get(id=variant_id)
        # currently just takes first hit from above query set.
        gene_symbol = ''
        chromosome = "chr" + getattr(variant, "chromosome")
        position = str(getattr(variant, "position"))
        assembly = str(getattr(variant, "genome_assembly"))
        print(assembly)
        designed_primers = singletarget.design_primers(chromosome, position, assembly, gene_symbol)
        count = 1
        # tool id currently not set properly
        for designed_primer in designed_primers:
            primer = Primer(variant=variant, primer_set=chromosome + ":" + position + "-" + str(count),
                            left_primer_seq=designed_primer.forward_seq, right_primer_seq=designed_primer.reverse_seq,
                            date_created=datetime.today(), tool_id=1)
            primer.save()
            # variant.primers.add(primer)
            # variant.save()
            print("primer added to database:")
            print(primer.primer_set)
            count += 1

    primers = Primer.objects.filter(variant=variant_id)
    variant = Variant.objects.get(id=variant_id)
    transcript_variant = TranscriptVariant.objects.filter(variant=variant_id)[:1].get() #gets one (for hgvs_g)
    proband_variants = ProbandVariant.objects.filter(variant=variant)

    return render(request, 'gel2mdt/variant.html', {'variant': variant,
                                                    'transcript_variant': transcript_variant,
                                                    'proband_variants': proband_variants,
                                                    'primers': primers})


@login_required
def update_proband(request, report_id):
    '''
    Updates the Proband page
    :param request:
    :param report_id: GEL Report ID
    :return:
    '''
    report = GELInterpretationReport.objects.get(id=report_id)
    if request.method == "POST":
        proband_form = ProbandForm(request.POST, instance=report.ir_family.participant_family.proband)

        if proband_form.is_valid():
            proband_form.save()
            messages.add_message(request, 25, 'Proband Updated')
            return HttpResponseRedirect(f'/proband/{report_id}')

@login_required
def select_transcript(request, report_id, pv_id):
    '''
    Shows the transcript table and allows a user to select preferred transcript
    :param request:
    :param pv_id:
    :return:
    '''
    proband_transcript_variants = ProbandTranscriptVariant.objects.filter(proband_variant__id=pv_id)
    # Just selecting first selected transcript
    selected_count = 0
    for ptv in proband_transcript_variants:
        if ptv.selected:
            if selected_count == 0:
                pass
            else:
                ptv.selected = False
                ptv.save()
            selected_count += 1
    report = GELInterpretationReport.objects.get(id=report_id)
    return render(request, 'gel2mdt/select_transcript.html',
                  {'proband_transcript_variants': proband_transcript_variants,
                   'report': report})

@login_required
def update_transcript(request, report_id, pv_id, transcript_id):
    '''
    Updates the selected transcript
    :param request:
    :param pv_id:
    :return:
    '''
    transcript = Transcript.objects.get(id=transcript_id)
    proband_variant = ProbandVariant.objects.get(id=pv_id)
    proband_variant.select_transcript(selected_transcript=transcript)
    messages.add_message(request, 25, 'Transcript Updated')
    return HttpResponseRedirect(f'/select_transcript/{report_id}/{proband_variant.id}')


@login_required
def add_variant(request, report_id):
    '''
    Adds a variant to a report
    :param request:
    :param report_id:
    :return:
    '''

    if request.method == 'POST':
        variant_form = VariantForm(request.POST)
        if variant_form.is_valid():
            report = GELInterpretationReport.objects.get(id=report_id)
            variant = CaseVariant(variant_form.cleaned_data['chromosome'],
                                  variant_form.cleaned_data['position'],
                                  report_id,
                                  1,
                                  variant_form.cleaned_data['reference'],
                                  variant_form.cleaned_data['alternate'],
                                  str(report.assembly))
            variant_entry = variant_form.save(commit=False)
            variant_entry.genome_assembly = report.assembly
            variant_entry.save()
            VariantAdder(variant_entry=variant_entry,
                         report=report,
                         variant=variant)
    else:
        variant_form = VariantForm()
    return render(request, 'gel2mdt/add_variant.html', {'variant_form': variant_form})


@login_required
def start_mdt_view(request):
    '''
    Creates a new MDT instance
    :param request:
    :return:
    '''
    mdt_instance = MDT(creator=request.user, date_of_mdt=datetime.now())
    mdt_instance.save()

    return HttpResponseRedirect(f'/edit_mdt/{mdt_instance.id}')


@login_required
def edit_mdt(request, mdt_id):
    '''
    Allows users to select which cases they want to bring to MDT
    :param request:
    :param mdt_id:
    :return:
    '''

    gel_ir_list = GELInterpretationReport.objects.all()
    mdt_instance = MDT.objects.get(id=mdt_id)
    reports_in_mdt = MDTReport.objects.filter(MDT=mdt_instance).values_list('interpretation_report', flat=True)

    return render(request, 'gel2mdt/mdt_ir_select.html', {'gel_ir_list': gel_ir_list,
                                                          'reports_in_mdt': reports_in_mdt,
                                                          'mdt_id': mdt_id})


@login_required
def add_ir_to_mdt(request, mdt_id, irreport_id):
    """
    :param request:
    :param mdt_id: MDT ID
    :param irreport_id: GelIR ID
    :return: Add this report to the MDT
    """
    if request.method == 'POST':
        mdt_instance = MDT.objects.get(id=mdt_id)
        report_instance = GELInterpretationReport.objects.get(id=irreport_id)
        linkage_instance = MDTReport(interpretation_report=report_instance,
                                     MDT=mdt_instance)
        linkage_instance.save()

        proband_variants = ProbandVariant.objects.filter(interpretation_report=report_instance)
        for pv in proband_variants:
            pv.create_rare_disease_report()

        return HttpResponseRedirect(f'/edit_mdt/{mdt_id}')


@login_required
def remove_ir_from_mdt(request, mdt_id, irreport_id):
    """
    Removes a proband from an MDT
    :param request:
    :param mdt_id: MDT ID
    :param irreport_id: GELIR ID
    :return: Removes this report from the MDT
    """
    if request.method=='POST':
        mdt_instance = MDT.objects.get(id=mdt_id)
        report_instance = GELInterpretationReport.objects.get(id=irreport_id)

        MDTReport.objects.filter(MDT=mdt_instance, interpretation_report=report_instance).delete()
        return HttpResponseRedirect(f'/edit_mdt/{mdt_id}')


@login_required
def mdt_view(request, mdt_id):
    """
    :param request:
    :param mdt_id: MDT ID
    :return: Main MDT page
    """
    mdt_instance = MDT.objects.get(id=mdt_id)
    report_list = MDTReport.objects.filter(MDT=mdt_instance).values_list('interpretation_report', flat=True)
    reports = GELInterpretationReport.objects.filter(id__in=report_list)

    proband_variants = ProbandVariant.objects.filter(interpretation_report__in=report_list)
    proband_variant_count = {}
    t3_proband_variant_count = {}
    for report in reports:
        count = ProbandVariant.objects.filter(interpretation_report=report,
                                              max_tier__lte=2).count()
        proband_variant_count[report.id] = count
        count = ProbandVariant.objects.filter(interpretation_report=report,
                                              max_tier=3).count()
        t3_proband_variant_count[report.id] = count

    mdt_form = MdtForm(instance=mdt_instance)
    clinicians = Clinician.objects.filter(mdt=mdt_id).values_list('name', flat=True)
    clinical_scientists = ClinicalScientist.objects.filter(mdt=mdt_id).values_list('name', flat=True)
    other_staff = OtherStaff.objects.filter(mdt=mdt_id).values_list('name', flat=True)

    attendees = list(clinicians) + list(clinical_scientists) + list(other_staff)
    if mdt_form["status"].value() == "C":
        for field in mdt_form.__dict__["fields"]:
            mdt_form.fields[field].widget.attrs['readonly'] = True
            mdt_form.fields[field].widget.attrs['disabled'] = True

    if request.method == 'POST':
        mdt_form = MdtForm(request.POST, instance=mdt_instance)

        if mdt_form.is_valid():
            mdt_form.save()
            messages.add_message(request, 25, 'MDT Updated')

        return HttpResponseRedirect(f'/mdt_view/{mdt_id}')
    request.session['mdt_id'] = mdt_id
    return render(request, 'gel2mdt/mdt_view.html', {'proband_variants': proband_variants,
                                                      'proband_variant_count': proband_variant_count,
                                                     't3_proband_variant_count': t3_proband_variant_count,
                                                      'reports': reports,
                                                      'mdt_form': mdt_form,
                                                      'mdt_id': mdt_id,
                                                      'attendees': attendees})

@login_required
def mdt_proband_view(request, mdt_id, pk, important):
    mdt_instance = MDT.objects.get(id=mdt_id)
    report = GELInterpretationReport.objects.get(id=pk)
    if important ==1:
        proband_variants = ProbandVariant.objects.filter(interpretation_report=report,
                                                         max_tier__lte=2).order_by('-max_tier')
    else:
        proband_variants = ProbandVariant.objects.filter(interpretation_report=report,
                                                         max_tier=3)
    proband_variant_reports = RareDiseaseReport.objects.filter(proband_variant__in=proband_variants)

    proband_form = ProbandMDTForm(instance=report.ir_family.participant_family.proband)
    VariantForm = modelformset_factory(RareDiseaseReport, form=RareDiseaseMDTForm, extra=0)
    variant_formset = VariantForm(queryset=proband_variant_reports)
    panels = InterpretationReportFamilyPanel.objects.filter(ir_family=report.ir_family)

    if mdt_instance.status == "C":
        for form in variant_formset.forms:
            for field in form.__dict__["fields"]:
                form.fields[field].widget.attrs['readonly'] = True
                form.fields[field].widget.attrs['disabled'] = True
        for field in proband_form.__dict__["fields"]:
            proband_form.fields[field].widget.attrs['readonly'] = True
            proband_form.fields[field].widget.attrs['disabled'] = True

    if request.method == 'POST':
        variant_formset = VariantForm(request.POST)
        proband_form = ProbandMDTForm(request.POST, instance=report.ir_family.participant_family.proband)
        if variant_formset.is_valid() and proband_form.is_valid():
            variant_formset.save()
            proband_form.save()
            messages.add_message(request, 25, 'Proband Updated')
        return HttpResponseRedirect(f'/mdt_proband_view/{mdt_id}/{pk}/{important}')
    return render(request, 'gel2mdt/mdt_proband_view.html', {'proband_variants': proband_variants,
                                                             'report': report,
                                                             'mdt_id': mdt_id,
                                                             'mdt_instance': mdt_instance,
                                                             'proband_form': proband_form,
                                                             'variant_formset': variant_formset,
                                                             'panels': panels})

@login_required
def edit_mdt_proband(request, report_id):
    """
    :param request:
    :param pk: Sample ID
    :return: Edits the proband discussion and actions in the MDT
    """
    data = {}
    report = GELInterpretationReport.objects.get(id=report_id)
    if request.method == 'POST':
        proband_form = ProbandMDTForm(request.POST,
                                      instance=report.ir_family.participant_family.proband)
        mdt_id = request.session.get('mdt_id')
        if proband_form.is_valid():
            proband_form.save()
            data['form_is_valid'] = True

            report_list = MDTReport.objects.filter(MDT=mdt_id).values_list('interpretation_report', flat=True)
            reports = GELInterpretationReport.objects.filter(id__in=report_list)
            proband_variant_count = {}
            t3_proband_variant_count = {}
            for report in reports:
                count = ProbandVariant.objects.filter(interpretation_report=report,
                                                      max_tier__lte=2).count()
                proband_variant_count[report.id] = count
                count = ProbandVariant.objects.filter(interpretation_report=report,
                                                      max_tier=3).count()
                t3_proband_variant_count[report.id] = count

            data['html_mdt_list'] = render_to_string('gel2mdt/includes/mdt_proband_table.html', {
                'reports': reports,
                'proband_variant_count': proband_variant_count,
                't3_proband_variant_count': t3_proband_variant_count,
                'mdt_id': request.session['mdt_id']
            })
        else:
            data['form_is_valid'] = False
            print(proband_form.errors)
    else:
        proband_form = ProbandMDTForm(instance=report.ir_family.participant_family.proband)

    context = {'proband_form': proband_form,
               'report':report}

    html_form = render_to_string('gel2mdt/modals/mdt_proband_form.html',
                                 context,
                                 request=request,
                                 )
    data['html_form'] = html_form
    return JsonResponse(data)


@login_required
def recent_mdts(request):
    '''
    Shows table of recent MDTs
    :param request:
    :return:
    '''
    recent_mdt = list(MDT.objects.all().order_by('-date_of_mdt'))

    # Need to get which probands were in MDT
    probands_in_mdt = {}
    for mdt in recent_mdt:
        probands_in_mdt[mdt.id] = []
        report_list = MDTReport.objects.filter(MDT=mdt.id)
        for report in report_list:
            probands_in_mdt[mdt.id].append((report.interpretation_report.id,
                                            report.interpretation_report.ir_family.participant_family.proband.gel_id))

    return render(request, 'gel2mdt/recent_mdts.html', {'recent_mdt': recent_mdt,
                                                        'probands_in_mdt': probands_in_mdt})

@login_required
def delete_mdt(request, mdt_id):
    '''
    Deletes a selected MDT
    :param request:
    :param mdt_id:
    :return: Back to recent MDTs
    '''
    if request.method == "POST":
        mdt_instance = MDT.objects.get(id=mdt_id)
        # Delete existing entrys in MDTReport:
        MDTReport.objects.filter(MDT=mdt_instance).delete()
        mdt_instance.delete()
        messages.error(request, 'MDT Deleted')
    return HttpResponseRedirect('/recent_mdts')

@login_required
def select_attendees_for_mdt(request, mdt_id):
    '''
    Adds a CS/Clinician/Other to a MDT
    :param request:
    :param mdt_id:
    :return: Table showing all users
    '''
    clinicians = (Clinician.objects.filter(added_by_user=True)
                  .values('name', 'email', 'hospital', 'id', 'mdt')
                  .distinct())
    clinical_scientists = (ClinicalScientist.objects.all()
                           .values('name', 'email', 'hospital', 'id', 'mdt')
                           .distinct())
    other_staff = (OtherStaff.objects.all()
                       .values('name', 'email', 'hospital', 'id', 'mdt')
                       .distinct())
    for clinician in clinicians:
        clinician['role'] = 'Clinician'
    for cs in clinical_scientists:
        cs['role'] = 'Clinical Scientist'
    for other in other_staff:
        other['role'] = 'Other Staff'
    attendees = list(clinicians) + list(clinical_scientists) + list(other_staff)
    currently_added_to_mdt = []
    for attendee in attendees:
        if attendee['mdt'] == mdt_id:
            currently_added_to_mdt.append(attendee['email'])
        attendee.pop('mdt')

    attendees = [dict(y) for y in set(tuple(x.items()) for x in attendees)]
    request.session['mdt_id'] = mdt_id
    return render(request, 'gel2mdt/select_attendee_for_mdt.html', {'attendees': attendees, 'mdt_id': mdt_id,
                                                                    'currently_added_to_mdt': currently_added_to_mdt})

@login_required
def add_attendee_to_mdt(request, mdt_id, attendee_id, role):
    '''

    :param request:
    :param mdt_id:
    :param attendee_id:
    :return:
    '''
    if request.method == 'POST':
        mdt_instance = MDT.objects.get(id=mdt_id)

        if role == 'Clinician':
            clinician = Clinician.objects.get(id=attendee_id)
            mdt_instance.clinicians.add(clinician)
            mdt_instance.save()
        elif role == 'Clinical Scientist':
            clinical_scientist = ClinicalScientist.objects.get(id=attendee_id)
            mdt_instance.clinical_scientists.add(clinical_scientist)
            mdt_instance.save()
        elif role == 'Other Staff':
            other = OtherStaff.objects.get(id=attendee_id)
            mdt_instance.other_staff.add(other)
            mdt_instance.save()
        return HttpResponseRedirect(f'/select_attendees_for_mdt/{mdt_id}')

@login_required
def remove_attendee_from_mdt(request, mdt_id, attendee_id, role):
    '''

    :param request:
    :param mdt_id:
    :param attendee_id:
    :return:
    '''
    if request.method == 'POST':
        mdt_instance = MDT.objects.get(id=mdt_id)
        if role == 'Clinician':
            clinician = Clinician.objects.get(id=attendee_id)
            mdt_instance.clinicians.remove(clinician)
        elif role == 'Clinical Scientist':
            clinical_scientist = ClinicalScientist.objects.get(id=attendee_id)
            mdt_instance.clinical_scientists.remove(clinical_scientist)
        elif role == 'Other Staff':
            other = OtherStaff.objects.get(id=attendee_id)
            mdt_instance.other_staff.remove(other)
        return HttpResponseRedirect(f'/select_attendees_for_mdt/{mdt_id}')

@login_required
def add_new_attendee(request):
    '''
    Add a new attendee to the 3 attendee models
    :param request:
    :return:
    '''
    if request.method == 'POST':

        form = AddNewAttendee(request.POST)
        if form.is_valid():
            if form.cleaned_data['role'] == 'Clinician':
                clinician, created = Clinician.objects.get_or_create(
                                      email=form.cleaned_data['email'])
                clinician.name=form.cleaned_data['name']
                clinician.hospital=form.cleaned_data['hospital']
                clinician.added_by_user=True
                clinician.save()
            elif form.cleaned_data['role'] == 'Clinical Scientist':
                cs, created = ClinicalScientist.objects.get_or_create(
                                       email=form.cleaned_data['email'])
                cs.name = form.cleaned_data['name']
                cs.hospital = form.cleaned_data['hospital']
                cs.save()
            elif form.cleaned_data['role'] == 'Other Staff':
                other, created = OtherStaff.objects.get_or_create(
                                   email=form.cleaned_data['email'])
                other.name = form.cleaned_data['name']
                other.hospital = form.cleaned_data['hospital']
                other.save()
            messages.add_message(request, 25, 'Attendee Added')
            if 'mdt_id' in request.session:
                return HttpResponseRedirect('/select_attendees_for_mdt/{}'.format(request.session.get('mdt_id')))
            else:
                return HttpResponseRedirect('/recent_mdts/')
    else:
        form = AddNewAttendee()
    return render(request, 'gel2mdt/add_new_attendee.html', {'form': form})

@login_required
def export_mdt(request, mdt_id):
    if request.method == "POST":
        mdt_instance = MDT.objects.get(id=mdt_id)
        mdt_reports = MDTReport.objects.filter(MDT=mdt_instance)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=MDT_{}.csv'.format(mdt_id)
        writer = csv.writer(response)
        writer = write_mdt_export(writer, mdt_instance, mdt_reports)
        return response

@login_required
def export_mdt_outcome_form(request, report_id):
    report = GELInterpretationReport.objects.get(id=report_id)
    document, mdt = write_mdt_outcome_template(report)
    f = BytesIO()
    document.save(f)
    length = f.tell()
    f.seek(0)
    response = HttpResponse(
        f.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

    filename = '{}_{}_{}_{}.docx'.format(report.ir_family.participant_family.proband.surname,
                                         report.ir_family.participant_family.proband.forename,
                                         report.ir_family.ir_family_id,
                                         mdt.date_of_mdt.date())
    response['Content-Disposition'] = 'attachment; filename=' + filename
    response['Content-Length'] = length
    return response

@login_required
def negative_report(request, report_id):
    '''
    Shows details about a particular proband, some fields are editable by clinical scientists
    :param request:
    :param report_id: GEL Report ID
    :return:
    '''
    config_dict = load_config.LoadConfig().load()

    report = GELInterpretationReport.objects.get(id=report_id)
    panels = InterpretationReportFamilyPanel.objects.filter(ir_family=report.ir_family)

    panel_genes = {}
    for panel in panels:
        panelapp_file = f'{config_dict["panelapp_storage"]}/{panel.panel.panel.panelapp_id}_{panel.panel.version_number}.json'
        if os.path.isfile(panelapp_file):
            panelapp_json = json.load(open(panelapp_file))
            num_genes = len(panelapp_json['result']['Genes'])
            panel_genes[panel] = num_genes
        else:
            panel_genes[panel] = ''


    return render(request, 'gel2mdt/technical_information.html', {
        'report': report,
        'panels': panel_genes})


@login_required
def genomics_england_report(request, report_id):
    """Render a page to enter genomics england samples """
    report = GELInterpretationReport.objects.get(id=report_id)
    cip_id = report.ir_family.ir_family_id.split('-')
    gel_content = get_gel_content(cip_id[0], cip_id[1])
    if gel_content:
        return render(request, 'gel2mdt/gel_template.html', {'gel_content': gel_content})
    else:
        messages.add_message(request, 40, 'Failed to generate report, does one exist?')
        return HttpResponseRedirect(f'/proband/{report_id}')

