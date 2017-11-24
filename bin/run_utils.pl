#!/usr/bin/env perl

use 5.10.0;
use strict;
use warnings;

use lib './lib';

use Getopt::Long;
use Path::Tiny qw/path/;
use Pod::Usage;
use YAML::XS qw/LoadFile/;
use DDP;

use Utils::CaddToBed;
use Utils::Fetch;
use Utils::LiftOverCadd;
use Utils::SortCadd;
use Utils::RenameTrack;
use Utils::FilterCadd;
use Utils::RefGeneXdbnsfp;

use Seq::Build;

# TODO: refactor to automatically call util by string value
# i.e: --util filterCadd launches Utils::FilterCadd
my (
  $yaml_config, $wantedName, $sortCadd, $filterCadd, $renameTrack,
  $help,        $liftOverCadd, $liftOverPath, $liftOverChainPath,
  $debug,       $overwrite, $fetch, $caddToBed, $compress, $toBed,
  $renameTrackTo, $verbose, $dryRunInsertions, $maxThreads,
);

# usage
GetOptions(
  'c|config=s'   => \$yaml_config,
  'n|name=s'     => \$wantedName,
  'h|help'       => \$help,
  'd|debug=i'      => \$debug,
  'o|overwrite'  => \$overwrite,
  'v|verbose=i' => \$verbose,
  'r|dryRun' => \$dryRunInsertions,
  'm|maxThreads=i' => \$maxThreads,
);

if ($help || !$yaml_config || !$wantedName) {
  Pod::Usage::pod2usage();
}

my %options = (
  config       => $yaml_config,
  name         => $wantedName,
  debug        => $debug,
  overwrite    => $overwrite || 0,
  verbose => $verbose,
  dryRun => $dryRunInsertions,
);

if($maxThreads) {
  $options{maxThreads} = $maxThreads;
}

my $config = LoadFile($yaml_config);
my $utilConfigs;
my $trackIdx = 0;

for my $track (@{$config->{tracks}}) {
  if($track->{name} eq $wantedName) {
    $utilConfigs = $track->{utils};
    last;
  }

  $trackIdx++;
}

if (!$utilConfigs) {
  die "The specified track must have 'utils' property";
}

for(my $utilIdx = 0; $utilIdx < @$utilConfigs; $utilIdx++) {
  # config may be mutated, by the last utility
  $config = LoadFile($yaml_config);
  my $utilConfig = $config->{tracks}[$trackIdx]{utils}[$utilIdx];

  my $utilName = $utilConfig->{name};

  # Uppercase the first letter of the utility class name
  # aka user may specify "fetch" and we grab Utils::Fetch
  my $className = 'Utils::' . uc( substr($utilName, 0, 1) ) . substr($utilName, 1, length($utilName) - 1); 
  my $args = $utilConfig->{args} || {};

  my %finalOpts = (%options, %$args, (utilIdx => $utilIdx));
 
  my $instance = $className->new(\%finalOpts);
  $instance->go();
}

__END__

=head1 NAME

run_utils - Runs items in lib/Utils

=head1 SYNOPSIS

run_utils
  --config <yaml>
  --name <track>
  [--debug]
  [--verbose]
  [--maxThreads]
  [--dryRun]
  [--overwrite]
  [--help]

=head1 DESCRIPTION

C<run_utils.pl> Lets you run utility functions in lib/Utils

=head1 OPTIONS

=over 8

=item B<-t>, B<--compress>

Flag to compress output files

=item B<-c>, B<--config>

Config: A YAML genome assembly configuration file that specifies the various
tracks and data associated with the assembly. This is the same file that is
used by the Seq Package to annotate snpfiles.

=item B<-w>, B<--name>

name: The name of the track in the YAML config file

=back

=head1 AUTHOR

Alex Kotlar

=head1 SEE ALSO

Seq Package

=cut
