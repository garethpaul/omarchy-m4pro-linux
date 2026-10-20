/* Host libalpm metadata preparation only. No commit, sysupgrade, payload load or execution. */
#include <alpm.h>
#include <alpm_list.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static char **protected_names, **allowed;
static size_t protected_count, allowed_count;
static int unexpected, fetch_attempts;
typedef struct { int type, answer; char *incoming, *retained; } question_record;
static question_record questions[1024];
static size_t question_count;

static void string(const char *s) {
    if(!s) { fputs("null",stdout); return; }
    putchar('"');
    for(const unsigned char *p=(const unsigned char *)s;*p;p++) {
        if(*p=='"'||*p=='\\') { putchar('\\'); putchar(*p); }
        else if(*p<32) printf("\\u%04x",*p);
        else putchar(*p);
    }
    putchar('"');
}
static void fatal(const char *s) { fputs(s,stderr); fputc('\n',stderr); exit(2); }
static char **lines(const char *path, size_t *count) {
    FILE *f=fopen(path,"r"); if(!f) fatal("cannot open bounded metadata input");
    char **result=NULL,*line=NULL; size_t capacity=0; ssize_t n;
    while((n=getline(&line,&capacity,f))>=0) {
        if(n>4096||*count>=20000) fatal("metadata input exceeds bound");
        while(n&&(line[n-1]=='\n'||line[n-1]=='\r')) line[--n]=0;
        if(!n) continue;
        char **next=realloc(result,(*count+1)*sizeof(*result)); if(!next) fatal("allocation failed");
        result=next; result[(*count)++]=strdup(line);
    }
    free(line); fclose(f); return result;
}
static int held(const char *name) {
    for(size_t i=0;i<protected_count;i++) if(!strcmp(name,protected_names[i])) return 1;
    return 0;
}
static int may_remove(const char *incoming,const char *retained) {
    if(held(incoming)||held(retained)) return 0;
    for(size_t i=0;i<allowed_count;i++) {
        const char *tab=strchr(allowed[i],'\t');
        if(tab&&(size_t)(tab-allowed[i])==strlen(incoming)&&!strncmp(incoming,allowed[i],(size_t)(tab-allowed[i]))&&!strcmp(retained,tab+1)) return 1;
    }
    return 0;
}
static int fetch(void *ctx,const char *url,const char *path,int force) {
    (void)ctx;(void)url;(void)path;(void)force; fetch_attempts++; return -1;
}
static void ask(void *ctx,alpm_question_t *q) {
    (void)ctx; const char *incoming=NULL,*retained=NULL; int answer=0;
    if(q->type==ALPM_QUESTION_CONFLICT_PKG) {
        incoming=alpm_pkg_get_name(q->conflict.conflict->package1);
        retained=alpm_pkg_get_name(q->conflict.conflict->package2);
        answer=may_remove(incoming,retained); q->conflict.remove=answer;
    } else if(q->type==ALPM_QUESTION_REPLACE_PKG) {
        incoming=alpm_pkg_get_name(q->replace.newpkg);retained=alpm_pkg_get_name(q->replace.oldpkg);
        answer=may_remove(incoming,retained);q->replace.replace=answer;
    } else {
        /* Unknown provider/key/ignore/skip decisions never qualify a scenario. */
        unexpected=1;
        if(q->type==ALPM_QUESTION_SELECT_PROVIDER) q->select_provider.use_index=0;
        else q->any.answer=0;
    }
    if(question_count<1024) questions[question_count++]=(question_record){q->type,answer,incoming?strdup(incoming):NULL,retained?strdup(retained):NULL};
    else unexpected=1;
}
static void packages(alpm_list_t *list) {
    putchar('['); int first=1;
    for(alpm_list_t *i=list;i;i=i->next) {
        alpm_pkg_t *pkg=i->data;if(!first) { putchar(','); }
        first=0;
        fputs("{\"name\":",stdout);string(alpm_pkg_get_name(pkg));fputs(",\"version\":",stdout);string(alpm_pkg_get_version(pkg));
        alpm_db_t *db=alpm_pkg_get_db(pkg);fputs(",\"repository\":",stdout);string(db?alpm_db_get_name(db):NULL);putchar('}');
    }
    putchar(']');
}
static void marker(const char *dir) {
    char *path=NULL; if(asprintf(&path,"%s/.abi-prepare-only",dir)<0) fatal("allocation failed");
    FILE *f=fopen(path,"r");free(path);if(!f) fatal("requires isolated metadata-only marker");
    char value[32];if(!fgets(value,sizeof(value),f)||strcmp(value,"metadata-only\n")) fatal("invalid isolation marker");fclose(f);
}
int main(int argc,char **argv) {
    if(argc!=7) fatal("usage: prepare ROOT DB TARGETS PROTECTED SCENARIO REPOSITORIES");
    marker(argv[1]);marker(argv[2]);
    protected_names=lines(argv[4],&protected_count);allowed=lines(argv[5],&allowed_count);
    alpm_errno_t initerr;alpm_handle_t *handle=alpm_initialize(argv[1],argv[2],&initerr);
    if(!handle) fatal(alpm_strerror(initerr));
    if(alpm_option_add_architecture(handle,"aarch64")||alpm_option_set_questioncb(handle,ask,NULL)||alpm_option_set_fetchcb(handle,fetch,NULL)) fatal("cannot configure isolated handle");
    /* Same Required DatabaseOptional policy as the frozen image, no key imports. */
    if(alpm_option_set_default_siglevel(handle,ALPM_SIG_PACKAGE|ALPM_SIG_DATABASE|ALPM_SIG_DATABASE_OPTIONAL)) fatal("cannot preserve signature policy");
    for(size_t i=0;i<protected_count;i++) if(alpm_option_add_ignorepkg(handle,protected_names[i])) fatal("cannot set held package");
    size_t repository_count=0,target_count=0;char **repositories=lines(argv[6],&repository_count),**targets=lines(argv[3],&target_count);
    alpm_db_t **dbs=calloc(repository_count,sizeof(*dbs));if(!dbs) fatal("allocation failed");
    for(size_t i=0;i<repository_count;i++) {
        dbs[i]=alpm_register_syncdb(handle,repositories[i],ALPM_SIG_USE_DEFAULT);if(!dbs[i]) fatal(alpm_strerror(alpm_errno(handle)));
    }
    int flags=ALPM_TRANS_FLAG_NOLOCK|ALPM_TRANS_FLAG_NEEDED;
    if(alpm_trans_init(handle,flags)) fatal(alpm_strerror(alpm_errno(handle)));
    for(size_t i=0;i<target_count;i++) {
        char *entry=targets[i],*repo=strsep(&entry,"\t"),*name=strsep(&entry,"\t"),*version=strsep(&entry,"\t");
        if(!repo||!name||!version||entry||held(name)) fatal("invalid or protected exact target");
        alpm_pkg_t *pkg=NULL;
        for(size_t j=0;j<repository_count;j++) if(!strcmp(repo,repositories[j])) pkg=alpm_db_get_pkg(dbs[j],name);
        if(!pkg||strcmp(alpm_pkg_get_version(pkg),version)) fatal("exact target metadata differs");
        if(alpm_add_pkg(handle,pkg)) fatal(alpm_strerror(alpm_errno(handle)));
    }
    alpm_list_t *data=NULL;int rc=alpm_trans_prepare(handle,&data);alpm_errno_t err=alpm_errno(handle);
    int protected_changed=0;
    for(alpm_list_t *i=alpm_trans_get_add(handle);i;i=i->next) if(held(alpm_pkg_get_name(i->data))) protected_changed=1;
    for(alpm_list_t *i=alpm_trans_get_remove(handle);i;i=i->next) if(held(alpm_pkg_get_name(i->data))) protected_changed=1;
    printf("{\"schema\":1,\"libalpm_version\":");string(alpm_version());
    printf(",\"prepared\":%s,\"prepare_exit\":%d,\"committed\":false,\"flags\":%d,\"dependency_checks\":true,\"conflict_checks\":true,\"unexpected_question\":%s,\"fetch_attempts\":%d,\"protected_changed\":%s,\"error\":",rc==0&&!unexpected&&!fetch_attempts&&!protected_changed?"true":"false",rc,flags,unexpected?"true":"false",fetch_attempts,protected_changed?"true":"false");
    if(rc) string(alpm_strerror(err));else fputs("null",stdout);
    fputs(",\"add\":",stdout);packages(alpm_trans_get_add(handle));fputs(",\"remove\":",stdout);packages(alpm_trans_get_remove(handle));
    fputs(",\"questions\":[",stdout);
    for(size_t i=0;i<question_count;i++) {
        if(i) { putchar(','); }
        printf("{\"type\":%d,\"answer\":%d,\"incoming\":",questions[i].type,questions[i].answer);string(questions[i].incoming);fputs(",\"retained\":",stdout);string(questions[i].retained);putchar('}');
    }
    fputs("],\"details\":[",stdout);int first=1;
    if(rc) for(alpm_list_t *i=data;i;i=i->next) {
        if(!first) { putchar(','); }
        first=0;
        if(err==ALPM_ERR_UNSATISFIED_DEPS) {
            alpm_depmissing_t *d=i->data;char *dep=alpm_dep_compute_string(d->depend);
            fputs("{\"target\":",stdout);string(d->target);fputs(",\"dependency\":",stdout);string(dep);fputs(",\"causing_package\":",stdout);string(d->causingpkg);putchar('}');free(dep);
        } else if(err==ALPM_ERR_CONFLICTING_DEPS) {
            alpm_conflict_t *c=i->data;char *dep=alpm_dep_compute_string(c->reason);fputs("{\"package1\":",stdout);string(alpm_pkg_get_name(c->package1));fputs(",\"package2\":",stdout);string(alpm_pkg_get_name(c->package2));fputs(",\"reason\":",stdout);string(dep);putchar('}');free(dep);
        } else string("unclassified prepare detail; scenario remains unqualified");
    }
    puts("]}");
    for(alpm_list_t *i=data;i;i=i->next) {
        if(err==ALPM_ERR_UNSATISFIED_DEPS) alpm_depmissing_free(i->data);
        else if(err==ALPM_ERR_CONFLICTING_DEPS) alpm_conflict_free(i->data);
        else if(err==ALPM_ERR_PKG_INVALID_ARCH) free(i->data);
    }
    alpm_list_free(data);
    alpm_trans_release(handle);alpm_release(handle);
    for(size_t i=0;i<question_count;i++) { free(questions[i].incoming);free(questions[i].retained); }
    for(size_t i=0;i<protected_count;i++) free(protected_names[i]);
    for(size_t i=0;i<allowed_count;i++) free(allowed[i]);
    for(size_t i=0;i<repository_count;i++) free(repositories[i]);
    for(size_t i=0;i<target_count;i++) free(targets[i]);
    free(protected_names);free(allowed);free(repositories);free(targets);free(dbs);return 0;
}
